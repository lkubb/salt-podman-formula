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
