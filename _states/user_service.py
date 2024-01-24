"""
State module specifically for managing user services, which is impossible
with the included modules. This was extracted from my ``compose`` modules.

A user session is required. Currently, this is achieved by requiring
having lingering enabled on the target user account.
Enabling lingering is only one method though, the other one using
machinectl / systemctl --user -M.

I forgot which problems I had using this method though.

https://github.com/saltstack/salt/issues/40887
"""

import time
from pathlib import Path
from salt.exceptions import CommandExecutionError, SaltInvocationError
from salt.utils.args import get_function_argspec as _argspec


def _get_valid_args(func, kwargs):
    valid_args = _argspec(func).args

    return {arg: kwargs[arg] for arg in valid_args if arg in kwargs}


def lingering_managed(name, enable):
    """
    Manage lingering status for a user.
    Lingering is required to run rootless containers as
    general services.

    name
        The user to manage lingering for.

    enable
        Whether to enable or disable lingering.
    """

    ret = {"name": name, "changes": {}, "result": True, "comment": ""}

    try:
        user_info = __salt__["user.info"](name)
        if not user_info:
            if __opts__["test"]:
                ret["result"] = None
                ret[
                    "comment"
                ] = f"User {name} does not exist. If it is created by some state before this, this check will pass."
                return ret
            raise SaltInvocationError(f"User {name} does not exist.")

        if enable:
            func = __salt__["user_service.lingering_enable"]
            verb = "enable"
        else:
            func = __salt__["user_service.lingering_disable"]
            verb = "disable"

        if __salt__["user_service.lingering_enabled"](name) is enable:
            ret["comment"] = f"Lingering for user {name} is already {verb}d."
            return ret
        if __opts__["test"]:
            ret["result"] = None
            ret["comment"] = f"Lingering for user {name} is set to be {verb}d."
            ret["changes"]["lingering"] = enable
        elif not func(name):
            raise CommandExecutionError(
                f"Something went wrong while trying to {verb} lingering for user {name}. "
                "This should not happen."
            )

        start = time.time()
        dbus_session_bus = Path(f"/run/user/{user_info['uid']}/bus")
        # The enabling lags a bit, which might make other states fail
        while start - time.time() < 10:
            if dbus_session_bus.exists() is enable:
                ret["comment"] = f"Lingering for user {name} has been {verb}d."
                ret["changes"]["lingering"] = enable
                return ret
            time.sleep(0.1)
        raise CommandExecutionError(
            "No errors encountered, but the reported state does not match the expected"
        )

    except (CommandExecutionError, SaltInvocationError) as e:
        ret["result"] = False
        ret["comment"] = str(e)

    return ret


def enabled(
    name,
    user=None,
):
    """
    Make sure a systemd unit is enabled.

    name
        Name of the systemd unit.

    user
        User account the unit should be enabled for. Defaults to Salt process user.
    """

    ret = {"name": name, "changes": {}, "result": True, "comment": ""}

    try:
        if __salt__["user_service.is_enabled"](
            name,
            user=user,
        ):
            ret["comment"] = f"Service {name} is already enabled."
            return ret

        if __opts__["test"]:
            ret["result"] = None
            ret["comment"] = f"Service {name} is set to be enabled."
            ret["changes"]["enabled"] = name
            return ret

        if __salt__["user_service.enable"](
            name,
            user=user,
        ):
            ret["comment"] = f"Service {name} has been enabled."
            ret["changes"]["enabled"] = name
        else:
            raise CommandExecutionError(
                f"Something went wrong while trying to stop service {name}. This should not happen."
            )

        if not __salt__["user_service.is_enabled"](
            name,
            user=user,
        ):
            ret["result"] = False
            ret[
                "comment"
            ] = "Tried to enable the service, but it is reported as disabled."
            ret["changes"] = {}

    except (CommandExecutionError, SaltInvocationError) as e:
        ret["result"] = False
        ret["comment"] = str(e)

    return ret


def running(name, user=None, enable=None, timeout=10):
    """
    Make sure a systemd unit is running.

    name
        Name of the systemd unit.

    user
        User account the unit should be running for. Defaults to Salt process user.

    enable
        Also ensure the unit is enabled (``True``) or disabled (``False``).
        By default, does not check enabled status.

    timeout
        This state checks whether the service was started successfully. Specify
        the maximum wait time in seconds. Defaults to 10.
    """

    ret = {"name": name, "changes": {}, "result": True, "comment": ""}

    try:
        enabled = None
        enable_str = "enable" if enable else "disable"
        actions = []
        running = __salt__["user_service.is_running"](
            name,
            user=user,
        )

        if enable is not None:
            enabled = __salt__["user_service.is_enabled"](
                name,
                user=user,
            )

        if running and enable is enabled:
            ret["comment"] = f"Service {name} is in the correct state."
            return ret

        if not running:
            actions.append("started")
        if enable is not enabled:
            actions.append(f"{enable_str}d")

        if __opts__["test"]:
            ret["result"] = None
            ret["comment"] = f"Service {name} would have been {' and '.join(actions)}."
            if not running:
                ret["changes"]["started"] = name
            if enable and enable is not enabled:
                ret["changes"][f"{enable_str}d"] = name
            return ret

        if not running:
            if __salt__["user_service.start"](
                name,
                user=user,
            ):
                ret["changes"]["started"] = name
            else:
                raise CommandExecutionError(
                    f"Something went wrong while trying to start service {name}. This should not happen."
                )

        if enable is not enabled:
            if __salt__[f"user_service.{enable_str}"](name, user=user):
                ret["changes"][f"{enable_str}d"] = name
            else:
                raise CommandExecutionError(
                    f"Something went wrong while trying to {enable_str} service {name}. This should not happen."
                )

        ret["comment"] = f"Service {name} has been {' and '.join(actions)}."

        if running:
            return ret

        start_time = time.time()

        while not __salt__["user_service.is_running"](
            name,
            user=user,
        ):
            if time.time() - start_time > timeout:
                ret["result"] = False
                ret[
                    "comment"
                ] = "Tried to start the service, but it is still not running."
                ret["changes"].pop("started")
                return ret
            time.sleep(0.25)

    except (CommandExecutionError, SaltInvocationError) as e:
        ret["result"] = False
        ret["comment"] = str(e)

    return ret


def disabled(
    name,
    user=None,
):
    """
    Make sure a systemd unit is disabled. This is an extension to the
    official module, which allows to manage services for arbitrary user accounts.
    This does not support mod_watch behavior. Also, it should be a separate module @TODO

    name
        Name of the systemd unit.

    user
        User account the unit should be disabled for. Defaults to Salt process user.
    """

    ret = {"name": name, "changes": {}, "result": True, "comment": ""}

    try:
        if not __salt__["user_service.is_enabled"](
            name,
            user=user,
        ):
            ret["comment"] = f"Service {name} is already disabled."
            return ret

        if __opts__["test"]:
            ret["result"] = None
            ret["comment"] = f"Service {name} is set to be disabled."
            ret["changes"]["disabled"] = name
            return ret

        if __salt__["user_service.disable"](
            name,
            user=user,
        ):
            ret["comment"] = f"Service {name} has been disabled."
            ret["changes"]["disabled"] = name
        else:
            raise CommandExecutionError(
                f"Something went wrong while trying to stop service {name}. This should not happen."
            )

        if __salt__["user_service.is_enabled"](
            name,
            user=user,
        ):
            ret["result"] = False
            ret[
                "comment"
            ] = "Tried to disable the service, but it is reported as enabled."
            ret["changes"] = {}

    except (CommandExecutionError, SaltInvocationError) as e:
        ret["result"] = False
        ret["comment"] = str(e)

    return ret


def dead(name, user=None, enable=None, timeout=10):
    """
    Make sure a systemd unit is dead. This is an extension to the
    official module, which allows to manage services for arbitrary user accounts.
    This does not support mod_watch behavior. Also, it should be a separate module @TODO

    name
        Name of the systemd unit.

    user
        User account the unit should be dead for. Defaults to Salt process user.

    enable
        Also ensure the unit is enabled (``True``) or disabled (``False``).
        By default, does not check enabled status.

    timeout
        This state checks whether the service was stopped successfully. Specify
        the maximum wait time in seconds. Defaults to 10.
    """

    ret = {"name": name, "changes": {}, "result": True, "comment": ""}

    try:
        enabled = None
        enable_str = "enable" if enable else "disable"
        actions = []
        running = __salt__["user_service.is_running"](
            name,
            user=user,
        )

        if enable is not None:
            enabled = __salt__["user_service.is_enabled"](
                name,
                user=user,
            )

        if not running and enable is enabled:
            ret["comment"] = f"Service {name} is in the correct state."
            return ret

        if running:
            actions.append("stopped")
        if enable is not enabled:
            actions.append(f"{enable_str}d")

        if __opts__["test"]:
            ret["result"] = None
            ret["comment"] = f"Service {name} would have been {' and '.join(actions)}."
            if running:
                ret["changes"]["stopped"] = name
            if enable and enable is not enabled:
                ret["changes"][f"{enable_str}d"] = name
            return ret

        if running:
            if __salt__["user_service.stop"](
                name,
                user=user,
            ):
                ret["changes"]["stopped"] = name
            else:
                raise CommandExecutionError(
                    f"Something went wrong while trying to stop service {name}. This should not happen."
                )

        if enable is not enabled:
            if __salt__[f"user_service.{enable_str}"](name, user=user):
                ret["changes"][f"{enable_str}d"] = name
            else:
                raise CommandExecutionError(
                    f"Something went wrong while trying to {enable_str} service {name}. This should not happen."
                )

        ret["comment"] = f"Service {name} has been {' and '.join(actions)}."

        if not running:
            return ret

        start_time = time.time()

        while __salt__["user_service.is_running"](
            name,
            user=user,
        ):
            if time.time() - start_time > timeout:
                ret["result"] = False
                ret["comment"] = "Tried to stop the service, but it is still running."
                ret["changes"] = {}
                return ret
            time.sleep(0.25)

    except (CommandExecutionError, SaltInvocationError) as e:
        ret["result"] = False
        ret["comment"] = str(e)

    return ret


def mod_watch(name, sfun=None, reload=False, **kwargs):
    ret = {"name": name, "changes": {}, "result": True, "comment": ""}
    pp_suffix = "ed"

    # all status functions have the same signature
    status_kwargs = _get_valid_args(__salt__["user_service.is_running"], kwargs)

    try:
        if sfun in ["dead", "running"]:
            if sfun == "dead":
                verb = "stop"
                pp_suffix = "ped"

                if __salt__["user_service.is_running"](name, **status_kwargs):
                    func = __salt__["user_service.stop"]
                    check_func = __salt__["user_service.is_dead"]
                else:
                    ret["comment"] = "Service is already stopped."
                    return ret

            # "running" == sfun evidently
            else:
                check_func = __salt__["user_service.is_running"]
                if __salt__["user_service.is_running"](name, **status_kwargs):
                    verb = "reload" if reload else "restart"
                    func = __salt__[f"user_service.{verb}"]
                else:
                    verb = "start"
                    func = __salt__["user_service.start"]

        else:
            ret["comment"] = f"Unable to trigger watch for user_service.{sfun}"
            ret["result"] = False
            return ret

        if __opts__["test"]:
            ret["result"] = None
            ret["comment"] = f"Service is set to be {verb}{pp_suffix}."
            ret["changes"][verb + pp_suffix] = name
            return ret

        func_kwargs = _get_valid_args(func, kwargs)
        func(name, **func_kwargs)

        timeout = kwargs.get("timeout", 10)
        start_time = time.time()

        while not check_func(name, **status_kwargs):
            if time.time() - start_time > timeout:
                ret["result"] = False
                ret[
                    "comment"
                ] = f"Tried to {verb} the service, but it is still not {sfun}."
                ret["changes"] = {}
                return ret
            time.sleep(0.25)

    except (CommandExecutionError, SaltInvocationError) as e:
        ret["result"] = False
        ret["comment"] = str(e)
        return ret

    ret["comment"] = f"Service was {verb}{pp_suffix}."
    ret["changes"][verb + pp_suffix] = name

    return ret
