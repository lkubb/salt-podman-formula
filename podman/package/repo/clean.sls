# -*- coding: utf-8 -*-
# vim: ft=sls

{%- set tplroot = tpldir.split('/')[0] %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}


{%- if podman.lookup.pkg_manager not in ['apt', 'dnf', 'yum', 'zypper'] %}
{%-   if salt['state.sls_exists'](slsdotpath ~ '.' ~ podman.lookup.pkg_manager ~ '.clean') %}

include:
  - {{ slsdotpath ~ '.' ~ podman.lookup.pkg_manager ~ '.clean' }}
{%-   endif %}

{%- else %}
{%-   for reponame, enabled in podman.lookup.enablerepo.items() %}
{%-     if enabled %}

Podman {{ reponame }} repository is absent:
  pkgrepo.absent:
{%-       for conf in ['name', 'ppa', 'ppa_auth', 'keyid', 'keyid_ppa', 'copr'] %}
{%-         if conf in podman.lookup.repos[reponame] %}
    - {{ conf }}: {{ podman.lookup.repos[reponame][conf] }}
{%-         endif %}
{%-       endfor %}
{%-     endif %}
{%-   endfor %}
{%- endif %}
