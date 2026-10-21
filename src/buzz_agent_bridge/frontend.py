"""Official ACP-v1 stdio frontend; end_turn means durable intake, not job completion."""
import argparse
import asyncio
from collections import defaultdict, deque
import logging
import time
import uuid

from acp import Agent, InitializeResponse, NewSessionResponse, PromptResponse
from acp import run_agent, text_block, update_agent_message
from acp.schema import (AgentCapabilities, Implementation, SessionConfigOptionSelect,
                        SessionConfigSelectOption, SetSessionConfigOptionResponse)

from . import VERSION
from .broker import AdmissionCancelled
from .framing import source_ids
from .ipc import LocalClient
from .providers import PRODUCT_ID, get_provider


class Frontend(Agent):
    def model_options(self):
        # Buzz requires a model selector for custom ACP runtimes. This one fixed
        # option names the remote conversation; it never starts a separate LLM.
        return [SessionConfigOptionSelect(id="model", name="Conversation", category="model",
            type="select", current_value=self.provider.id, options=[SessionConfigSelectOption(
                value=self.provider.id, name=self.provider.name,
                description=self.provider.description)])]

    def __init__(self, client, short_wait=0.2, *, provider=None):
        if not 0 <= short_wait <= 1:
            raise ValueError("Short wait must be at most one second")
        self.client, self.short_wait = client, short_wait
        self.provider = (provider or get_provider()).info
        self.sessions, self.queued, self.active = set(), defaultdict(deque), {}
        self.conn = None

    def observe(self, event):
        """Use the SDK's public observer hook; retain IDs only, never log frames."""
        message = event.message
        if getattr(event.direction, "value", event.direction) == "incoming":
            params = message.get("params") or {}
            session = params.get("sessionId")
            if message.get("method") == "session/prompt" and session in self.sessions:
                self.queued[session].append({"jsonrpc_id": message.get("id"),
                    "admission_id": uuid.uuid4().hex, "cancelled": False})
        else:
            # Drop observer metadata for a malformed request rejected by SDK validation.
            ident = message.get("id")
            if ident is not None and "error" in message:
                for session, items in self.queued.items():
                    self.queued[session] = deque(row for row in items if row["jsonrpc_id"] != ident)

    def on_connect(self, conn):
        self.conn = conn

    async def initialize(self, protocol_version, **kwargs):
        return InitializeResponse(protocol_version=1, agent_capabilities=AgentCapabilities(),
                                  agent_info=Implementation(name=PRODUCT_ID, version=VERSION))

    async def new_session(self, cwd, mcp_servers=None, **kwargs):
        if len(self.sessions) >= 1000:
            raise ValueError("Session capacity reached")
        session = uuid.uuid4().hex
        self.sessions.add(session)
        return NewSessionResponse(session_id=session, config_options=self.model_options())

    async def set_config_option(self, config_id, session_id, value, **kwargs):
        if (session_id not in self.sessions or config_id != "model"
                or not self.provider.accepts_model(value)):
            raise ValueError("Only the configured remote agent is supported")
        return SetSessionConfigOptionResponse(config_options=self.model_options())

    async def _call(self, method, args):
        return await asyncio.to_thread(self.client.call, method, args)

    async def prompt(self, session_id, prompt, **kwargs):
        if session_id not in self.sessions or session_id in self.active:
            raise ValueError("Unknown or busy session")
        ticket = self.queued[session_id].popleft() if self.queued[session_id] else {
            "jsonrpc_id": None, "admission_id": uuid.uuid4().hex, "cancelled": False}
        self.active[session_id] = ticket
        try:
            ids = source_ids(prompt)
            if ticket["cancelled"]:
                return PromptResponse(stop_reason="cancelled")
            accepted = await self._call("admit", {
                "source_ids": ids, "session_id": session_id, "admission_id": ticket["admission_id"],
                "jsonrpc_id": ticket["jsonrpc_id"]})
            if accepted.get("durably_accepted") is not True:
                raise RuntimeError("Durable intake unconfirmed")
            jobs = accepted["jobs"]
            deadline = time.monotonic() + self.short_wait
            while (not ticket["cancelled"] and time.monotonic() < deadline
                   and any(job["delivery"] not in ("delivered", "suppressed", "uncertain", "quarantined")
                           for job in jobs)):
                await asyncio.sleep(min(.05, max(0, deadline - time.monotonic())))
                jobs = (await self._call("status", {"ids": [job["request_id"] for job in jobs]}))["jobs"]
            if ticket["cancelled"]:
                # ACP cancellation closes this interaction. Accepted remote jobs
                # continue; only explicit authenticated job cancellation fences them.
                return PromptResponse(stop_reason="cancelled")
            delivered = sum(job["delivery"] == "delivered" for job in jobs)
            text = (f"{len(jobs)} durable job(s) accepted; {delivered} result(s) delivered. "
                    "This ACP turn is ending; pending remote work and delivery remain tracked.")
            if delivered != len(jobs):
                await self.conn.session_update(session_id=session_id,
                    update=update_agent_message(text_block(text)))
            return PromptResponse(stop_reason="end_turn")
        except AdmissionCancelled:
            return PromptResponse(stop_reason="cancelled")
        except asyncio.CancelledError:
            await self._cancel_ticket(ticket)
            raise
        except Exception:
            raise RuntimeError("Durable intake unavailable; outcome may require reconciliation") from None
        finally:
            self.active.pop(session_id, None)

    async def _cancel_ticket(self, ticket):
        ticket["cancelled"] = True
        try:
            await self._call("cancel_admission", {"admission_id": ticket["admission_id"]})
        except Exception:
            pass  # Never claim that accepted remote work stopped.

    async def cancel(self, session_id, **kwargs):
        tickets = list(self.queued[session_id])
        if session_id in self.active:
            tickets.append(self.active[session_id])
        await asyncio.gather(*(self._cancel_ticket(ticket) for ticket in tickets))

    async def disconnect(self):
        await asyncio.gather(*(self.cancel(session_id) for session_id in list(self.sessions)))


async def serve(path, provider="chatgpt-dot"):
    frontend = Frontend(LocalClient(path), provider=get_provider(provider))
    try:
        await run_agent(frontend, observers=[frontend.observe], stdio_buffer_limit_bytes=262144)
    finally:
        await frontend.disconnect()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--provider", default="chatgpt-dot")
    args = parser.parse_args()
    # SDK exception diagnostics can include malformed input. Use sanitized errors
    # above and never emit raw library traceback/frame logs in this executable.
    logging.disable(logging.CRITICAL)
    asyncio.run(serve(args.socket, args.provider))


if __name__ == "__main__":
    main()
