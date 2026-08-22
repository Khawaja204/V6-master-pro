{ pkgs }: {
  deps = [
    pkgs.pari
    pkgs.python310Full
    pkgs.python310Packages.pip
    pkgs.git
  ];
}
