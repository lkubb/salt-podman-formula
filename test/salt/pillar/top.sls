# vim: ft=yaml
---
base:
  '*':
    - default
  'G@os_family:Gentoo':
    - gentoo
  'os:*':
    - define_roles
...
