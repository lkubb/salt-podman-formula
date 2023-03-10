# vim: ft=sls

{#-
    Removes the symlink from the expected Docker socket
    to the actual Podman socket.
#}

{%- set tplroot = tpldir.split("/")[0] %}
{%- set sls_package_install = tplroot ~ ".package.install" %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

Podman socket is not symlinked to docker socket:
  file.absent:
    - name: {{ podman.lookup.salt_compat.sockets.docker }}
    - onlyif:
      - fun: file.is_link
        path: {{ podman.lookup.salt_compat.sockets.docker }}
