# vim: ft=sls

{%- set tplroot = tpldir.split("/")[0] %}
{%- set sls_package_install = tplroot ~ ".package.install" %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

include:
  - {{ sls_package_install }}

Required packages to manage podman are installed:
  pkg.installed:
    - pkgs: {{ podman.lookup.salt_compat.pkgs | json }}
  pip.installed:
    - pkgs: {{ podman.lookup.salt_compat.pips | json }}
    - reload_modules: true

{%- if podman.python_install_method == "pip" %}

Restart salt minion on installation of docker-py:
  cmd.run:
    - name: 'salt-call service.restart salt-minion'
    - bg: true
    - onchanges:
      - pip: Required packages to manage podman are installed
{%- endif %}

Podman socket is symlinked to docker socket:
  file.symlink:
    - name: {{ podman.lookup.salt_compat.sockets.docker }}
    - target: {{ podman.lookup.salt_compat.sockets.podman }}
    - require:
      - sls: {{ sls_package_install }}
