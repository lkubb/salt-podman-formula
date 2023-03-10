# vim: ft=sls

{#-
    This state will install the configured podman repository.
    This works for apt/dnf/yum/zypper-based distributions only by default.
#}

{%- set tplroot = tpldir.split("/")[0] %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

include:
{%- if podman.lookup.pkg_manager in ["apt", "dnf", "yum", "zypper"] %}
  - {{ slsdotpath }}.install
{%- elif salt["state.sls_exists"](slsdotpath ~ "." ~ podman.lookup.pkg_manager) %}
  - {{ slsdotpath }}.{{ podman.lookup.pkg_manager }}
{%- else %}
  []
{%- endif %}
