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


