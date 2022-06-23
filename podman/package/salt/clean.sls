# -*- coding: utf-8 -*-
# vim: ft=sls

{%- set tplroot = tpldir.split('/')[0] %}
{%- set sls_package_install = tplroot ~ '.package.install' %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}
{%- from tplroot ~ "/libtofs.jinja" import files_switch with context %}

Podman socket is not symlinked to docker socket:
  file.absent:
    - name: {{ podman.lookup.salt_compat.sockets.docker }}
    - onlyif:
      - fun: file.is_link
        path: {{ podman.lookup.salt_compat.sockets.docker }}
