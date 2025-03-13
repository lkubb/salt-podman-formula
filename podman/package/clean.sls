# vim: ft=sls

{#-
    Removes Podman and possibly podman-compose/docker-compose
    and has a dependency on `podman.config.clean`_.
#}

{%- set tplroot = tpldir.split("/")[0] %}
{%- set sls_config_clean = tplroot ~ ".config.clean" %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

include:
  - {{ sls_config_clean }}
{%- if "repo" == podman.install_method %}
  - {{ slsdotpath }}.repo.clean
{%- endif %}
{%- if podman.salt_compat %}
  - {{ slsdotpath }}.salt.clean
{%- endif %}

Podman is removed:
  pkg.removed:
    - name: {{ podman.lookup.pkg.name }}
    - require:
      - sls: {{ sls_config_clean }}

Podman unit files are absent:
  file.absent:
    - names:
      - {{ podman.lookup.service.path.format(name=podman.lookup.service.name) }}
      - {{ podman.lookup.service.socket_path.format(name=podman.lookup.service.name) }}

{%- if "Debian" == grains.os and "pkg" == podman.install_method %}
{%-   if podman.debian_experimental %}

Debian experimental repository is inactive:
  pkgrepo.absent:
    - humanname: Debian experimental
    - name: deb http://deb.debian.org/debian/ experimental main contrib non-free
    - file: /etc/apt/sources.list

Debian repositories are unpinned:
  file.absent:
    - name: /etc/apt/preferences.d/99pin-experimental
{%-   elif podman.debian_unstable %}

Debian unstable repository is inactive:
  pkgrepo.absent:
    - humanname: Debian unstable
    - name: deb http://deb.debian.org/debian/ unstable main contrib non-free
    - file: /etc/apt/sources.list

Debian repositories are unpinned:
  file.absent:
    - name: /etc/apt/preferences.d/99pin-unstable
{%-   endif %}
{%- endif %}

{%- if podman.compose.install %}
{%-   if "docker" == podman.compose.install %}

docker-compose is absent:
  file.absent:
    - name: /usr/local/bin/docker-compose
{%-   elif "podman" == podman.compose.install %}
{%-     if grains.os_family == "Debian" and (grains.osmajorrelease >=12 or (grains.os == "Ubuntu" and grains.osmajorrelease >=23)) %}

podman-compose is absent:
  cmd.run:
    - name: pipx uninstall podman-compose
    - env:
        PIPX_HOME: /opt/pipx
        PIPX_BIN_DIR: /usr/local/bin
        PIPX_MAN_DIR: /usr/local/share/man
    - onlyif:
      - pipx list --short | grep podman-compose

{%-     else %}
{%-       set pip =
            salt["cmd.which_bin"](["/bin/pip3", "/usr/bin/pip3", "/bin/pip", "/usr/bin/pip"]) or
            '__slot__:salt:cmd.which_bin(["/bin/pip3", "/usr/bin/pip3", "/bin/pip", "/usr/bin/pip"])'
%}

podman-compose is absent:
  pip.removed:
    - name: {{ podman.lookup.compose.podman.pip }}
    - bin_env: {{ pip }}
{%-     endif %}
{%-   endif %}
{%- endif %}
