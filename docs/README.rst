.. _readme:

Podman Formula
==============

|img_sr| |img_pc|

.. |img_sr| image:: https://img.shields.io/badge/%20%20%F0%9F%93%A6%F0%9F%9A%80-semantic--release-e10079.svg
   :alt: Semantic Release
   :scale: 100%
   :target: https://github.com/semantic-release/semantic-release
.. |img_pc| image:: https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white
   :alt: pre-commit
   :scale: 100%
   :target: https://github.com/pre-commit/pre-commit

Manage Podman with Salt.

This formula can also install ``docker-compose``/``podman-compose`` and make Podman work with the ``docker`` Salt execution/state module, as far as podman is compatible with the API.

Currently, it is only tested (manually) on Debian 11+, Rocky Linux, Fedora 38+ and SUSE. Other distributions are definitely in scope and will be added at some point.

.. contents:: **Table of Contents**
   :depth: 1

General notes
-------------

See the full `SaltStack Formulas installation and usage instructions
<https://docs.saltstack.com/en/latest/topics/development/conventions/formulas.html>`_.

If you are interested in writing or contributing to formulas, please pay attention to the `Writing Formula Section
<https://docs.saltstack.com/en/latest/topics/development/conventions/formulas.html#writing-formulas>`_.

If you want to use this formula, please pay attention to the ``FORMULA`` file and/or ``git tag``,
which contains the currently released version. This formula is versioned according to `Semantic Versioning <http://semver.org/>`_.

See `Formula Versioning Section <https://docs.saltstack.com/en/latest/topics/development/conventions/formulas.html#versioning>`_ for more details.

If you need (non-default) configuration, please refer to:

- `how to configure the formula with map.jinja <map.jinja.rst>`_
- the ``pillar.example`` file
- the `Special notes`_ section

Special notes
-------------
* The Debian 11 stable repository packages an outdated version of ``podman``, hence the possibility to enable ``sid`` or ``experimental`` (discouraged, might break your system).
* Rootless support currently depends on the package, I have observed some difficulty with the more current package in ``sid``.

Configuration
-------------
An example pillar is provided, please see `pillar.example`. Note that you do not need to specify everything by pillar. Often, it's much easier and less resource-heavy to use the ``parameters/<grain>/<value>.yaml`` files for non-sensitive settings. The underlying logic is explained in `map.jinja`.


Available states
----------------

The following states are found in this formula:

.. contents::
   :local:


``podman``
^^^^^^^^^^
*Meta-state*.

This installs Podman,
manages the Podman configuration,
possibly starts the podman socket
and creates and starts configured containers
with their rootless user accounts.


``podman.package``
^^^^^^^^^^^^^^^^^^
Installs the Podman package and possibly podman-compose/docker-compose.


``podman.package.repo``
^^^^^^^^^^^^^^^^^^^^^^^
This state will install the configured podman repository.
This works for apt/dnf/yum/zypper-based distributions only by default.


``podman.package.salt``
^^^^^^^^^^^^^^^^^^^^^^^
Installs necessary requirements to be able to somewhat
use the Salt ``docker`` modules with Podman.

See also: https://github.com/saltstack/salt/issues/50624#issuecomment-668495953


``podman.config``
^^^^^^^^^^^^^^^^^
Manages the Podman configuration.
Has a dependency on `podman.package`_.


``podman.service``
^^^^^^^^^^^^^^^^^^
Starts the podman service and enables it at boot time.
Has a dependency on `podman.config`_.


``podman.containers``
^^^^^^^^^^^^^^^^^^^^^
*Meta-state*.

Manages rootless user accounts, creates configured
containers, secrets and installs and runs the containers
using systemd service units.


``podman.containers.package``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Manages rootless user accounts, creates configured
containers, secrets and installs the containers as services.
Has a dependency on `podman.config`_ or `podman.service`_.,
depending on if any container runs rootful or not.


``podman.containers.service``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Starts the configured containers' services.
Has a dependency on `podman.containers.package`_.


``podman.clean``
^^^^^^^^^^^^^^^^
*Meta-state*.

Undoes everything performed in the ``podman`` meta-state
in reverse order, i.e.
stops and deletes configured containers and their rootless user accounts,
possibly stops the podman socket,
removes the Podman configuration and
uninstalls the Podman package.


``podman.package.clean``
^^^^^^^^^^^^^^^^^^^^^^^^
Removes Podman and possibly podman-compose/docker-compose
and has a dependency on `podman.config.clean`_.


``podman.package.repo.clean``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
This state will remove the configured podman repository.
This works for apt/dnf/yum/zypper-based distributions only by default.


``podman.package.salt.clean``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Removes the symlink from the expected Docker socket
to the actual Podman socket.


``podman.config.clean``
^^^^^^^^^^^^^^^^^^^^^^^
Removes the Podman configuration and has a
dependency on `podman.service.clean`_.


``podman.service.clean``
^^^^^^^^^^^^^^^^^^^^^^^^
Stops the podman service and disables it at boot time.


``podman.containers.clean``
^^^^^^^^^^^^^^^^^^^^^^^^^^^
*Meta-state*.

Undoes everything performed in the ``podman.compose`` meta-state
in reverse order, i.e.
stops and removes the configured containers' services,
removes configured secrets and containers,
removes rootless user accounts.


``podman.containers.package.clean``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Removes rootless user accounts, configured
containers, secrets and the containers' unit files.
Has a dependency on `podman.containers.service.clean`_.


``podman.containers.service.clean``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Stops the configured containers' services.



Contributing to this repo
-------------------------

Commit messages
^^^^^^^^^^^^^^^

**Commit message formatting is significant!**

Please see `How to contribute <https://github.com/saltstack-formulas/.github/blob/master/CONTRIBUTING.rst>`_ for more details.

pre-commit
^^^^^^^^^^

`pre-commit <https://pre-commit.com/>`_ is configured for this formula, which you may optionally use to ease the steps involved in submitting your changes.
First install  the ``pre-commit`` package manager using the appropriate `method <https://pre-commit.com/#installation>`_, then run ``bin/install-hooks`` and
now ``pre-commit`` will run automatically on each ``git commit``. ::

  $ bin/install-hooks
  pre-commit installed at .git/hooks/pre-commit
  pre-commit installed at .git/hooks/commit-msg

State documentation
~~~~~~~~~~~~~~~~~~~
There is a script that semi-autodocuments available states: ``bin/slsdoc``.

If a ``.sls`` file begins with a Jinja comment, it will dump that into the docs. It can be configured differently depending on the formula. See the script source code for details currently.

This means if you feel a state should be documented, make sure to write a comment explaining it.

Testing
-------

Linux testing is done with ``kitchen-salt``.

Requirements
^^^^^^^^^^^^

* Ruby
* Docker

.. code-block:: bash

   $ gem install bundler
   $ bundle install
   $ bin/kitchen test [platform]

Where ``[platform]`` is the platform name defined in ``kitchen.yml``,
e.g. ``debian-9-2019-2-py3``.

``bin/kitchen converge``
^^^^^^^^^^^^^^^^^^^^^^^^

Creates the docker instance and runs the ``podman`` main state, ready for testing.

``bin/kitchen verify``
^^^^^^^^^^^^^^^^^^^^^^

Runs the ``inspec`` tests on the actual instance.

``bin/kitchen destroy``
^^^^^^^^^^^^^^^^^^^^^^^

Removes the docker instance.

``bin/kitchen test``
^^^^^^^^^^^^^^^^^^^^

Runs all of the stages above in one go: i.e. ``destroy`` + ``converge`` + ``verify`` + ``destroy``.

``bin/kitchen login``
^^^^^^^^^^^^^^^^^^^^^

Gives you SSH access to the instance for manual testing.

Todo
----
* better rootless support

.. code-block:: yaml

   #(apt)
   rootless:
     - dbus-user-session
     - slirp4netns
     - uidmap
     - fuse-overlayfs # kernels < 5.11


   #(dnf)
   rootless:
     - dbus-daemon # dbus-user-session
     - slirp4netns
     - shadow-utils # uidmap

References
----------
* https://rootlesscontaine.rs
