# -*- coding: utf-8 -*-
# vim: ft=yaml
---
podman:
  lookup:
    master: template-master
    # Just for testing purposes
    winner: lookup
    added_in_lookup: lookup_value
    enablerepo:
      stable: true
    config: '/etc/containers'
    compose:
      docker:
        compose_version: 2.6.1
        latest:
          hash: https://github.com/docker/compose/releases/download/v{version}/docker-compose-linux-x86_64.sha256
          source: https://github.com/docker/compose/releases/download/v{version}/docker-compose-linux-x86_64
        legacy:
          hash: https://github.com/docker/compose/releases/download/1.29.2/docker-compose-linux-x86_64.sha256
          source: https://github.com/docker/compose/releases/download/1.29.2/docker-compose-linux-x86_64
        legacy_versions:
          - '1'
          - '2'
          - '3'
          - '4.0'
      podman:
        legacy_versions:
          - '1'
          - '2'
          - '3.0'
        pip: podman-compose
        pip_legacy: podman-compose==0.1.11
        repo: https://github.com/containers/podman-compose
    config_files:
      containers: containers.conf
      mounts: mounts.conf
      policy: policy.json
      registries: registries.conf
      seccomp: /usr/share/containers/seccomp.json
      storage: storage.conf
    pip_pkg: python3-pip
    salt_compat:
      pips:
        - docker
      pkgs:
        - python3-pip
      sockets:
        docker: /var/run/docker.sock
        podman: /var/run/podman/podman.sock
    service:
      name: podman
      path: /etc/systemd/system/{name}.service
      socket_path: /etc/systemd/system/{name}.socket
  compose:
    install: false
    install_modules: false
    podman_compose_rev: false
  config:
    global:
      containers:
        containers: {}
        engine: {}
        machine: {}
        network: {}
        secret: {}
        service_destinations: {}
      mounts: []
      policy:
        default:
          - type: insecureAcceptAnything
      registries:
        registry: []
        unqualified-search-registries:
          - docker.io
      storage: {}
    user: {}
  debian_experimental: false
  debian_unstable: false
  install_method: pkg
  salt_compat: false
  service_enable: false
  version: latest

  tofs:
    # The files_switch key serves as a selector for alternative
    # directories under the formula files directory. See TOFS pattern
    # doc for more info.
    # Note: Any value not evaluated by `config.get` will be used literally.
    # This can be used to set custom paths, as many levels deep as required.
    files_switch:
      - any/path/can/be/used/here
      - id
      - roles
      - osfinger
      - os
      - os_family
    # All aspects of path/file resolution are customisable using the options below.
    # This is unnecessary in most cases; there are sensible defaults.
    # Default path: salt://< path_prefix >/< dirs.files >/< dirs.default >
    #         I.e.: salt://podman/files/default
    # path_prefix: template_alt
    # dirs:
    #   files: files_alt
    #   default: default_alt
    # The entries under `source_files` are prepended to the default source files
    # given for the state
    # source_files:
    #   podman-config-file-file-managed:
    #     - 'example_alt.tmpl'
    #     - 'example_alt.tmpl.jinja'

    # For testing purposes
    source_files:
      podman-config-file-file-managed:
        - 'example.tmpl.jinja'

  # Just for testing purposes
  winner: pillar
  added_in_pillar: pillar_value
