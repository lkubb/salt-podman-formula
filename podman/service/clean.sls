# -*- coding: utf-8 -*-
# vim: ft=sls

{%- set tplroot = tpldir.split('/')[0] %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

podman-service-clean-service-dead:
  service.dead:
    - name: {{ podman.lookup.service.name }}.socket
    - enable: False
