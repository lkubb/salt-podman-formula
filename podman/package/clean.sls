# -*- coding: utf-8 -*-
# vim: ft=sls

{%- set tplroot = tpldir.split('/')[0] %}
{%- set sls_config_clean = tplroot ~ '.config.clean' %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

include:
  - {{ sls_config_clean }}
{%- if "repo" == podman.install_method %}
  - {{ slsdotpath }}.repo.clean
{%- endif %}
{%- if podman.salt_compat %}
  - {{ slsdotpath }}.salt.clean
{%- endif %}

podman-package-clean-pkg-removed:
  pkg.removed:
    - name: {{ podman.lookup.pkg.name }}
    - require:
      - sls: {{ sls_config_clean }}

Podman unit files are absent:
  file.absent:
    - names:
      - {{ podman.lookup.service.path.format(name=podman.lookup.service.name) }}
      - {{ podman.lookup.service.socket_path.format(name=podman.lookup.service.name) }}

{%- if podman.enable_debian_unstable and "Debian" == grains.os and "pkg" == podman.install_method %}

Debian unstable repository is inactive:
  pkgrepo.absent:
    - humanname: Debian unstable
    - name: deb http://deb.debian.org/debian/ unstable main contrib non-free
    - file: /etc/apt/sources.list

Debian repositories are unpinned:
  file.absent:
    - name: /etc/apt/preferences.d/99pin-unstable
{%- endif %}

{%- if podman.compose %}
{%-   if "docker" == podman.compose %}

docker-compose is absent:
  file.absent:
    - name: /usr/local/bin/docker-compose
{%-   elif "podman" == podman.compose %}

podman-compose is absent:
  pip.removed:
    - name: {{ podman._compose }}
{%-   endif %}
{%- endif %}
