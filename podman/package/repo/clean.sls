# vim: ft=sls

{#-
    This state will remove the configured podman repository.
    This works for apt/dnf/yum/zypper-based distributions only by default.
#}

{%- set tplroot = tpldir.split("/")[0] %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}


{%- if podman.lookup.pkg_manager not in ["apt", "dnf", "yum", "zypper"] %}
{%-   if salt["state.sls_exists"](slsdotpath ~ "." ~ podman.lookup.pkg_manager ~ ".clean") %}

include:
  - {{ slsdotpath ~ "." ~ podman.lookup.pkg_manager ~ ".clean" }}
{%-   endif %}

{%- else %}
{%-   set reponame = podman.lookup.enablerepo %}
{%-   set config = podman.lookup.repos[reponame] %}

Podman {{ reponame }} repository is absent:
  pkgrepo.absent:
{%-   for conf in ["name", "ppa", "ppa_auth", "keyid", "keyid_ppa", "copr"] %}
{%-     if conf in config %}
    - {{ conf }}: {{ config[conf] }}
{%-     endif %}
{%-   endfor %}
{%- endif %}
