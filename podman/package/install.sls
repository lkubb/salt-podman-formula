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

podman-package-install-pkg-installed:
  pkg.installed:
    - name: {{ podman.lookup.pkg.name }}

Toml python library is installed:
  pip.installed:
    - name: toml
    - reload_modules: true

Restart salt minion on installation of toml:
  cmd.run:
    - name: 'salt-call service.restart salt-minion'
    - bg: true
    - onchanges:
      - pip: toml

{%- if podman.salt_compat or podman.service_enable %}

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
{%- endif %}
