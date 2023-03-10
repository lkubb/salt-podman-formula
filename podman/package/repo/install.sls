# vim: ft=sls

{%- set tplroot = tpldir.split("/")[0] %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}
{%- from tplroot ~ "/libtofs.jinja" import files_switch with context %}

{%- if grains["os"] in ["Debian", "Ubuntu"] %}

# There is no need for python-apt anymore.
Ensure Podman APT repository can be managed:
  pkg.installed:
    - pkgs:
      - gnupg # to dearmor the keys @TODO this is not required anymore
{%- endif %}

{%- for reponame, config in podman.lookup.repos.items() %}
{%-   if reponame == podman.lookup.enablerepo %}

{%-     if "apt" == podman.lookup.pkg_manager %}
{%-       set tmpfile = salt["temp.file"]() %}

Podman {{ reponame }} signing key is available:
  file.managed:
    - name: {{ tmpfile }}
    - source: {{ files_switch([salt["file.basename"](config.keyring.file)],
                          lookup="Podman " ~ reponame ~ " signing key is available")
              }}
      - {{ config.keyring.source }}
{%-       if config.keyring.source_hash is false %}
    - skip_verify: true
{%-       else %}
    - source_hash: {{ config.keyring.source_hash }}
{%-       endif %}
    - user: root
    - group: {{ podman.lookup.rootgroup }}
    - mode: '0644'
    - dir_mode: '0755'
    - makedirs: true
    - unless:
      - fun: file.file_exists
        path: {{ config.keyring.file }}
  cmd.run:
    - name: >-
        mkdir -p '{{ salt["file.dirname"](config.keyring.file) }}' &&
        cat '{{ tmpfile }}' | gpg --dearmor > '{{ config.keyring.file }}'
    - onchanges:
      - file: {{ tmpfile }}
    - require:
      - Ensure Podman APT repository can be managed
    - require_in:
      - Podman {{ reponame }} repository is available
{%-     endif %}

Podman {{ reponame }} repository is available:
  pkgrepo.managed:
{%-     for conf, val in config.items() %}
{%-       if conf != "keyring" %}
    - {{ conf }}: {{ val }}
{%-       endif %}
{%-     endfor %}
{%-     if podman.lookup.pkg_manager in ["dnf", "yum", "zypper"] %}
    - enabled: 1
{%-     elif "apt" == podman.lookup.pkg_manager %}
    # This state module is not actually idempotent in many circumstances
    # https://github.com/saltstack/salt/pull/61986
    # workaround for this formula
    - unless:
      - fun: file.file_exists
        path: {{ config.file }}
{%-     endif %}
    - require_in:
      - Podman is installed

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

{%-     if "apt" == podman.lookup.pkg_manager %}

Podman {{ reponame }} signing key is absent:
  file.absent:
    - name: {{ config.keyring.file }}
{%-     endif %}
{%-   endif %}
{%- endfor %}
