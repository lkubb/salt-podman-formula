# vim: ft=sls

{%- set tplroot = tpldir.split("/")[0] %}
{%- set sls_package_install = tplroot ~ ".package.install" %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

include:
  - {{ sls_package_install }}

{%- if grains | traverse("selinux:enabled") %}
{%-   if podman.selinux.boolean.values() | reject("none") | list %}

SELinux booleans for Podman are managed:
  selinux.boolean:
    - names:
{%-     for name, val in podman.selinux.boolean.items() %}
{%-       if val is none %}
{%-         continue %}
{%-       endif %}
      - {{ name }}:
        - value: {{ val | to_bool }}
{%-     endfor %}
    - persist: true
    - require:
      - sls: {{ sls_package_install }}
{%-   endif %}
{%- endif %}
