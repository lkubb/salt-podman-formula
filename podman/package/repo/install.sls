# vim: ft=sls

{%- set tplroot = tpldir.split("/")[0] %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

{%- for reponame, config in podman.lookup.repos.items() %}
{%-   if reponame == podman.lookup.enablerepo %}

Podman {{ reponame }} repository is available:
  pkgrepo.managed:
{%-     for conf, val in config.items() %}
    - {{ conf }}: {{ val }}
{%-     endfor %}
{%-     if podman.lookup.pkg_manager in ["dnf", "yum", "zypper"] %}
    - enabled: 1
    - require_in:
      - Podman is installed
{%-     endif %}

{%-   else %}

Podman {{ reponame }} repository is disabled:
  pkgrepo.absent:
{%-     for conf in ["name", "ppa", "ppa_auth", "keyid", "keyid_ppa", "copr"] %}
{%-       if conf in config %}
    - {{ conf }}: {{ config[conf] }}
{%-       endif %}
{%-     endfor %}
    - require_in:
      - Podman is installed
{%-   endif %}
{%- endfor %}
