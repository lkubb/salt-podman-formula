# -*- coding: utf-8 -*-
# vim: ft=sls

{%- set tplroot = tpldir.split('/')[0] %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}
{%- from tplroot ~ "/libtofs.jinja" import files_switch with context %}

{%- if "repo" == podman.install_method or podman.salt_compat %}
include:
{%-   if "repo" == podman.install_method %}
  - {{ slsdotpath }}.repo
{%-   endif %}
{%-   if podman.salt_compat %}
  - {{ slsdotpath }}.salt
{%-   endif %}
{%- endif %}

{%- if "Debian" == grains.os and "pkg" == podman.install_method %}
{%-   if podman.debian_experimental %}

Debian experimental repository is active:
  pkgrepo.managed:
    - humanname: Debian experimental
    - name: deb http://deb.debian.org/debian experimental main contrib non-free
    - file: /etc/apt/sources.list
    - require_in:
      - podman-package-install-pkg-installed

Debian experimental repository is pinned to low priority to not install all experimental packages:
  file.managed:
    - name: /etc/apt/preferences.d/99pin-experimental
    - contents: |
        Package: *
        Pin: release a=stable
        Pin-Priority: 900

        Package: *
        Pin: release a=experimental
        Pin-Priority: 10
    - require_in:
      - podman-package-install-pkg-installed
{%-   elif podman.debian_unstable %}

Debian unstable repository is active:
  pkgrepo.managed:
    - humanname: Debian unstable
    - name: deb http://deb.debian.org/debian unstable main contrib non-free
    - file: /etc/apt/sources.list
    - require_in:
      - podman-package-install-pkg-installed

Debian unstable repository is pinned to low priority to not install all unstable packages:
  file.managed:
    - name: /etc/apt/preferences.d/99pin-unstable
    - contents: |
        Package: *
        Pin: release a=stable
        Pin-Priority: 900

        Package: *
        Pin: release a=unstable
        Pin-Priority: 20
    - require_in:
      - podman-package-install-pkg-installed
{%-   endif %}
{%- endif %}

{%- if "pkg" == podman.install_method and "Debian" == grains.os and podman.debian_unstable %}

podman-package-install-pkg-installed:
  pkg.installed:
    - pkgs: {{ podman.lookup.pkg.unstable }}

{%- elif "repo" == podman.install_method and podman.lookup.enablerepo in podman.lookup.pkg %}

podman-package-install-pkg-installed:
  pkg.installed:
    - pkgs: {{ podman.lookup.pkg[podman.lookup.enablerepo] }}

{%-   else %}

podman-package-install-pkg-installed:
  pkg.installed:
    - name: {{ podman.lookup.pkg.name }}
{%-   endif %}

# this installs pip and git, which are required for this formula
Podman required packages are installed:
  pkg.installed:
    - pkgs: {{ podman.lookup.required_pkgs }}

Toml python library is installed:
  pip.installed:
    - name: toml
    - reload_modules: true
    - require:
      - Podman required packages are installed

Restart salt minion on installation of toml:
  cmd.run:
    - name: 'salt-call service.restart salt-minion'
    - bg: true
    - onchanges:
      - pip: toml

# those are installed by the Debian package automatically
Podman unit files are installed:
  file.managed:
    - names:
      - {{ podman.lookup.service.path.format(name=podman.lookup.service.name) }}:
        - source: {{ files_switch(['podman.service'],
                                  lookup='Podman service unit file is installed',
                                  indent_width=10
                     )
                  }}
      - {{ podman.lookup.service.socket_path.format(name=podman.lookup.service.name) }}:
        - source: {{ files_switch(['podman.socket'],
                                  lookup='Podman socket unit file is installed',
                                  indent_width=10
                     )
                  }}
    - template: jinja
    - mode: '0644'
    - user: root
    - group: {{ podman.lookup.rootgroup }}
    - require:
      - podman-package-install-pkg-installed
    - context:
        podman: {{ podman | json }}
{%-   if 'systemctl' | which %}
  # this executes systemctl daemon-reload
  module.run:
    - service.systemctl_reload: []
    - onchanges:
      - file: {{ podman.lookup.service.path.format(name=podman.lookup.service.name) }}
      - file: {{ podman.lookup.service.socket_path.format(name=podman.lookup.service.name) }}
{%-   endif %}

{%- if podman.compose.install %}
{%-   if "docker" == podman.compose.install %}

docker-compose is installed:
  file.managed:
    - name: /usr/local/bin/docker-compose
    - source: {{ podman._compose.source }}
    - source_hash: {{ podman._compose.hash }}
    - mode: '0755'
    - user: root
    - group: {{ podman.lookup.rootgroup }}
    - require:
      - podman-package-install-pkg-installed
{%-   elif "podman" == podman.compose.install %}

podman-compose is installed:
  pip.installed:
    - name: {{ podman._compose }}
    - require:
      - podman-package-install-pkg-installed
      - Podman required packages are installed
{%-   endif %}
{%- endif %}

{%- if podman.compose.install_modules %}

Custom compose Salt modules are installed:
  saltutil.sync_all:
    - refresh: true
    - unless:
      - {{ "compose" in salt["saltutil.list_extmods"]().get("states", []) | lower }}
{%- endif %}
