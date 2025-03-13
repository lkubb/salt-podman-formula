# vim: ft=sls

{%- set tplroot = tpldir.split("/")[0] %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}
{%- from tplroot ~ "/libtofsstack.jinja" import files_switch with context %}

{%- if podman.install_method == "repo" or podman.salt_compat %}
include:
{%-   if podman.install_method == "repo" %}
  - {{ slsdotpath }}.repo
{%-   endif %}
{%-   if podman.salt_compat %}
  - {{ slsdotpath }}.salt
{%-   endif %}
{%- endif %}

{%- if grains.os == "Debian" and podman.install_method == "pkg" %}
{%-   if podman.debian_experimental %}

Debian experimental repository is active:
  pkgrepo.managed:
    - humanname: Debian experimental
    - name: deb http://deb.debian.org/debian experimental main contrib non-free
    - file: /etc/apt/sources.list
    - require_in:
      - Podman is installed

Debian experimental repository is pinned to low priority to not install all experimental packages:
  file.managed:
    - name: /etc/apt/preferences.d/99pin-experimental
    - contents: |
        Package: *
        Pin: release a=stable
        Pin-Priority: 900

        Package: *
        Pin: release a=experimental
        Pin-Priority: 10
    - require_in:
      - Podman is installed
{%-   elif podman.debian_unstable %}

Debian unstable repository is active:
  pkgrepo.managed:
    - humanname: Debian unstable
    - name: deb http://deb.debian.org/debian unstable main contrib non-free
    - file: /etc/apt/sources.list
    - require_in:
      - Podman is installed

Debian unstable repository is pinned to low priority to not install all unstable packages:
  file.managed:
    - name: /etc/apt/preferences.d/99pin-unstable
    - contents: |
        Package: *
        Pin: release a=stable
        Pin-Priority: 900

        Package: *
        Pin: release a=unstable
        Pin-Priority: 20
    - require_in:
      - Podman is installed
{%-   endif %}
{%- endif %}

{%- if podman.install_method == "pkg" and grains.os == "Debian" and podman.debian_unstable %}

Podman is installed:
  pkg.installed:
    - pkgs: {{ podman.lookup.pkg.unstable }}

{%- elif podman.install_method == "repo" and podman.lookup.enablerepo in podman.lookup.pkg %}

Podman is installed:
  pkg.installed:
    - pkgs: {{ podman.lookup.pkg[podman.lookup.enablerepo] }}

{%- else %}

Podman is installed:
  pkg.installed:
    - name: {{ podman.lookup.pkg.name }}
{%- endif %}

# this installs pip and git, which are required for this formula
Podman required packages are installed:
  pkg.installed:
    - pkgs: {{ podman.lookup.required_pkgs }}
{%- if podman.python_install_method == "pkg" %}
    - reload_modules: true
{%- endif %}

{%- if podman.python_install_method == "pip" %}

Toml and Podman python libraries are installed:
  pip.installed:
    - pkgs:
      - toml
      - podman
    - reload_modules: true
    - require:
      - Podman required packages are installed

Restart salt minion on installation of toml:
  cmd.run:
    - name: sleep 60; salt-call service.restart salt-minion
    - bg: true
    - onchanges:
      - Toml and Podman python libraries are installed
{%- endif %}

# those are installed by the distribution packages automatically
{%- if podman.lookup.service.install_unit_files %}
Podman unit files are installed:
  file.managed:
    - names:
      - {{ podman.lookup.service.path.format(name=podman.lookup.service.name) }}:
        - source: {{ files_switch(
                        ["podman.service", "podman.service.j2"],
                        config=podman,
                        lookup="Podman service unit file is installed",
                        indent_width=10
                     )
                  }}
      - {{ podman.lookup.service.socket_path.format(name=podman.lookup.service.name) }}:
        - source: {{ files_switch(
                        ["podman.socket", "podman.socket.j2"],
                        config=podman,
                        lookup="Podman socket unit file is installed",
                        indent_width=10
                     )
                  }}
    - template: jinja
    - mode: '0644'
    - user: root
    - group: {{ podman.lookup.rootgroup }}
    - require:
      - Podman is installed
    - context:
        podman: {{ podman | json }}
{%- endif %}

{%- if podman.compose.install %}
{%-   if podman.compose.install == "docker" %}

docker-compose is installed:
  file.managed:
    - name: /usr/local/bin/docker-compose
    - source: {{ podman._compose.source }}
    - source_hash: {{ podman._compose.hash }}
    - mode: '0755'
    - user: root
    - group: {{ podman.lookup.rootgroup }}
    - require:
      - Podman is installed

{%-   elif podman.compose.install == "podman" %}
{%-     if grains.os_family == "Debian" and (grains.osmajorrelease >=12 or (grains.os == "Ubuntu" and grains.osmajorrelease >=23)) %}
{#-       Dirty workaround for the system python being marked as externally managed @TODO migrate most to pipx + update pipx modules #}

pipx is installed:
  pkg.installed:
    - name: pipx

podman-compose is installed:
  cmd.run:
    - name: pipx install podman-compose
    - env:
        PIPX_HOME: /opt/pipx
        PIPX_BIN_DIR: /usr/local/bin
        PIPX_MAN_DIR: /usr/local/share/man
    - unless:
      - pipx list --short | grep podman-compose

{%-     else %}
{%-       set pip =
            salt["cmd.which_bin"](["/bin/pip3", "/usr/bin/pip3", "/bin/pip", "/usr/bin/pip"]) or
            '__slot__:salt:cmd.which_bin(["/bin/pip3", "/usr/bin/pip3", "/bin/pip", "/usr/bin/pip"])'
%}

podman-compose is installed:
  pip.installed:
    - name: {{ podman._compose }}
    - bin_env: {{ pip }}
    - require:
      - Podman is installed
      - Podman required packages are installed
{%-     endif %}
{%-   endif %}
{%- endif %}

{%- if podman.compose.install_modules %}

Custom compose Salt modules are installed:
  saltutil.sync_all:
    - refresh: true
    - unless:
      - '{{ ("compose" in salt["saltutil.list_extmods"]().get("states", [])) | lower }}'
{%- endif %}
