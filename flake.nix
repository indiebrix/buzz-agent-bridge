{
  description = "Portable development tools for Buzz Agent Bridge";

  # flake.lock pins the exact release archive and its NAR hash.
  inputs.nixpkgs.url = "https://channels.nixos.org/nixos-26.05/nixexprs.tar.xz";

  outputs = { nixpkgs, ... }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
      toolsFor = system:
        let
          pkgs = import nixpkgs { inherit system; };
          python = pkgs.python311;
        in {
          inherit pkgs python;
          packages = [ python pkgs.git pkgs.direnv pkgs.gitleaks pkgs.shellcheck ];
        };
    in {
      devShells = forAllSystems (system:
        let tools = toolsFor system;
        in {
          default = tools.pkgs.mkShellNoCC {
            inherit (tools) packages;
            # Package installation and virtualenv activation are explicit steps.
            PYTHONNOUSERSITE = "1";
          };
        });

      checks = forAllSystems (system:
        let tools = toolsFor system;
        in {
          development-tools = tools.pkgs.runCommand "bridge-development-tools" {
            nativeBuildInputs = tools.packages;
          } ''
            python -c 'import sys, venv, ensurepip; assert sys.version_info[:2] == (3, 11)'
            git --version
            direnv version
            gitleaks version
            shellcheck --shell=bash ${./.envrc} ${./scripts/check_nix_environment.sh}
            touch "$out"
          '';
        });
    };
}
