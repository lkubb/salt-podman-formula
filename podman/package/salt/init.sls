# vim: ft=sls

{#-
    Installs necessary requirements to be able to somewhat
    use the Salt ``docker`` modules with Podman.

    See also: https://github.com/saltstack/salt/issues/50624#issuecomment-668495953
#}

include:
  - .install
