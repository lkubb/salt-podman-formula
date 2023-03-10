"""
State module to interface with Podman through its REST API.

This is **very** basic at the moment and mostly wraps the
``podman`` Python module API.

All commands can target the system ``podman`` running as root
or a rootless ``podman`` running under a user account.

Note that the rootless API service usually requires lingering to be
enabled for the user account.

:depends: ``podman`` Python module
"""

import logging

from salt.exceptions import CommandExecutionError

log = logging.getLogger(__name__)

__virtualname__ = "podman"


def __virtual__():
    try:
        __salt__["podman.exists"]
    except KeyError:
        return False, "The `podman` execution module was not loaded"
    return __virtualname__


def absent(
    name,
    volumes=False,
    force=False,
    user=None,
):
    """
    Ensure that a container with this name does not exist.

    name
        The name of the container. Required.

    volumes
        Delete associated volumes as well. Defaults to false.

    force
        Kill a running container before deleting. Defaults to false.

    user
        Apply to rootless containers under this user account.
    """
    ret = {"name": name, "changes": {}, "result": True, "comment": ""}

    try:
        containers = __salt__["podman.ps"](all=True, user=user)
        exists = False
        for container in containers:
            if name in container["Names"]:
                exists = True
                break

        if not exists:
            ret["comment"] = f"A container named `{name}` does not exist"
            return ret

        if __opts__["test"]:
            ret["result"] = None
            ret["comment"] = "Would have removed the container"
            ret["changes"] = {"removed": name}
            return ret

        __salt__["podman.rm"](
            name=name,
            volumes=volumes,
            force=force,
            user=user,
        )
        ret["changes"] = {"removed": name}

    except CommandExecutionError as err:
        ret["result"] = False
        ret["comment"] = str(err)

    return ret


def dead(
    name,
    timeout=None,
    user=None,
):
    """
    Ensure that a container is not running.

    name
        The name of the container. Required.

    timeout
        Seconds to wait for container to stop before killing container.

    user
        Apply to rootless containers under this user account.
    """
    ret = {"name": name, "changes": {}, "result": True, "comment": ""}

    try:
        containers = __salt__["podman.ps"](all=True, user=user)
        exists = False
        state = None
        for container in containers:
            if name in container["Names"]:
                exists = True
                state = container["State"]
                break

        if not exists:
            ret["result"] = False
            ret["comment"] = f"A container named `{name}` does not exist"

        if state != "running":
            # Other states? @TODO
            ret["comment"] = f"A container named `{name}` is not running"
            return ret

        if __opts__["test"]:
            ret["result"] = None
            ret["comment"] = "Would have stopped the container"
            ret["changes"] = {"stopped": name}
            return ret

        __salt__["podman.stop"](
            name,
            timeout=timeout,
            user=user,
        )
        ret["changes"] = {"stopped": name}
        # @TODO check if stopped

    except CommandExecutionError as err:
        ret["result"] = False
        ret["comment"] = str(err)

    return ret


def present(
    name,
    image,
    command=None,
    user=None,
    **kwargs,
):
    """
    Ensure that a container with this name is present. This will not check
    existing containers for compliance with the specified configuration. @TODO

    name
        The name of the container. Required.

    image
        The image to base the container on. Required.

    command
        Command to run in the container.

    user
        Create a rootless container under this user account. Requires the Podman
        socket to run for this user, which usually requires lingering enabled.

    kwargs
        Keyword arguments that are passed to the ``create`` method of the
        ContainersManager instance.

        https://github.com/containers/podman-py/blob/main/podman/domain/containers_create.py
    """
    ret = {"name": name, "changes": {}, "result": True, "comment": ""}

    try:
        containers = __salt__["podman.ps"](all=True, user=user)
        exists = False
        for container in containers:
            if name in container["Names"]:
                exists = True
                break

        if exists:
            ret["comment"] = f"A container named `{name}` is already present"
            return ret

        if __opts__["test"]:
            ret["result"] = None
            ret["comment"] = "Would have created the container"
            ret["changes"] = {"created": name}
            return ret

        # some parameters need the patched function currently
        suffix = ""
        for param in ("secret_env",):
            if param in kwargs:
                suffix = "_patched"

        __salt__[f"podman.create{suffix}"](
            image,
            command=command,
            name=name,
            user=user,
            **kwargs,
        )
        ret["changes"] = {"created": name}

    except CommandExecutionError as err:
        ret["result"] = False
        ret["comment"] = str(err)

    return ret


def running(
    name,
    image,
    command=None,
    remove=False,
    stdout=True,
    stderr=False,
    user=None,
    **kwargs,
):
    """
    Ensure that a container is running. If it exists, but is not running,
    will be started without checking the parameters. To ensure changes are
    applied, you should rely on ``auto_remove: true``. This will not check
    running containers for compliance with the specified configuration.

    name
        The name of the container. Required.

    image
        The image to base the container on. Required.

    command
        Command to run in the container.

    remove
        Delete the container after the container's processes have finished. Defaults to False.

    stdout
        Include stdout output in the return. Defaults to True.

    stderr
        Include stderr output in the return. Defaults to False.

    user
        Run a rootless container under this user account. Requires the Podman
        socket to run for this user, which usually requires lingering enabled.

    kwargs
        Keyword arguments that are passed to the ``create`` method of the
        ContainersManager instance.

        https://github.com/containers/podman-py/blob/main/podman/domain/containers_create.py
    """
    ret = {"name": name, "changes": {}, "result": True, "comment": ""}

    try:
        containers = __salt__["podman.ps"](all=True, user=user)
        exists = False
        state = None
        for container in containers:
            if name in container["Names"]:
                exists = True
                state = container["State"]
                break

        if exists and state == "running":
            ret["comment"] = f"A container named `{name}` is already running"
            return ret

        if exists:
            func, past = (
                ("unpause", "unpaused") if state == "paused" else ("start", "started")
            )

            if __opts__["test"]:
                ret["changes"][past] = name
                ret["result"] = None
                ret["comment"] = f"Would have {past} the existing container"
                return ret

            __salt__[f"podman.{func}"](name, user=user)
            ret["changes"][past] = name
            ret["comment"] = f"The existing container was {past}"
            return ret

        if __opts__["test"]:
            ret["result"] = None
            ret["comment"] = "Would have created and started the container"
            ret["changes"] = {"created": name, "started": name}
            return ret

        res = __salt__["podman.run"](
            image,
            command=command,
            name=name,
            remove=remove,
            stdout=stdout,
            stderr=stderr,
            user=user,
            **kwargs,
        )
        ret["changes"] = {"created": name, "started": name, "output": res}

    except CommandExecutionError as err:
        ret["result"] = False
        ret["comment"] = str(err)

    return ret


def secret_absent(
    name,
    user=None,
):
    """
    Ensure that a secret with this name does not exist.

    name
        The name of the secret. Required.

    user
        Apply to Podman running under this user account.
    """
    ret = {"name": name, "changes": {}, "result": True, "comment": ""}

    try:
        exists = __salt__["podman.secret_exists"](name, user=user)

        if not exists:
            ret["comment"] = f"A secret named `{name}` does not exist"
            return ret

        if __opts__["test"]:
            ret["result"] = None
            ret["comment"] = "Would have removed the secret"
            ret["changes"] = {"removed": name}
            return ret

        __salt__["podman.remove_secret"](
            name=name,
            user=user,
        )
        ret["changes"] = {"removed": name}

    except CommandExecutionError as err:
        ret["result"] = False
        ret["comment"] = str(err)

    return ret


def secret_present(
    name,
    data,
    overwrite=False,
    driver=None,
    user=None,
):
    """
    Ensure a secret is present.

    name
        The name of the secret. Required.

    data
        The data the secret should contain. Required.

    overwrite
        Overwrite an existing secret. This might be necessary
        if the values should be updated. There is currently no
        (easy) way to check the secret that is stored in Podman.
        Defaults to false.

    driver
        The secret driver to use. Defaults to ``file`` (Podman default).

    user
        Create a rootless container under this user account. Requires the Podman
        socket to run for this user, which usually requires lingering enabled.
    """
    ret = {"name": name, "changes": {}, "result": True, "comment": ""}

    try:
        verb = "create"
        exists = __salt__["podman.secret_exists"](name, user=user)

        if exists and not overwrite:
            ret["comment"] = f"A secret named `{name}` is already present"
            return ret

        if exists:
            verb = "update"

        if __opts__["test"]:
            ret["result"] = None
            ret["comment"] = f"Would have {verb}d the secret"
            ret["changes"] = {f"{verb}d": name}
            return ret

        if exists:
            # Cannot overwrite existing secrets
            __salt__["podman.remove_secret"](name, user=user)

        __salt__["podman.create_secret"](
            name,
            data=data,
            driver=driver,
            user=user,
        )
        ret["changes"] = {f"{verb}d": name}

    except CommandExecutionError as err:
        ret["result"] = False
        ret["comment"] = str(err)

    return ret
