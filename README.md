# dbus-homewizard - Shows HomeWizard energy meters in Venus OS

This driver reads HomeWizard energy meters over HTTPS and shows each meter as a native energy meter on a Victron GX device.

GitHub repository: `https://github.com/<owner>/<repo>`. The owner of the repository replaces `<owner>/<repo>` in this file with the real GitHub path.

## Index

1. [Disclaimer](#disclaimer)
1. [Purpose](#purpose)
1. [HomeWizard setup](#homewizard-setup)
1. [Configuration](#configuration)
1. [Roles](#roles)
1. [Offline behavior](#offline-behavior)
1. [TLS and VerifyTls](#tls-and-verifytls)
1. [Install / Update](#install--update)
1. [Uninstall](#uninstall)
1. [Restart](#restart)
1. [Debugging](#debugging)
1. [Compatibility](#compatibility)
1. [Versioning](#versioning)


## Disclaimer

The author wrote this driver for personal use. The author is not responsible for any damage that this driver causes.


## Purpose

The driver supports these HomeWizard products:

- P1 Meter (`HWE-P1`)
- 1-phase kWh meter (`HWE-KWH1`, `SDM230-wifi`)
- 3-phase kWh meter (`HWE-KWH3`, `SDM630-wifi`)

For each meter, the driver registers the D-Bus service `com.victronenergy.<role>.homewizard_<serial>`. The role is the one that you choose on the GX screen. The serial is the serial number of the meter.

The GX screen and VRM show these values:

- Power in total and per phase
- Voltage and current
- Frequency
- Energy import and energy export, in kWh, from the meter itself

The driver runs one process for all meters. Each meter polls in its own thread, so a slow meter does not block the others.

The driver does not control the meters or any device behind them.


## HomeWizard setup

Set up each meter before you configure the driver.

1. **Fixed IP address.** Give each meter a fixed IP address in your router. The driver uses this address from `config.ini`. If the address changes, the driver cannot reach the meter. If your network resolves a host name, you can enter that name in `Host`.

1. **Firmware with API v2.** The driver uses the HomeWizard API v2 only. The meter must answer `GET https://<address>/api` with `"api_version": "v2"`.

1. **Token.** The driver needs a token for each meter. Run `pair.py` on the GX device after you install the driver. Follow the steps below.

    ```bash
    python3 /data/etc/dbus-homewizard/pair.py 192.168.1.30
    ```

    The tool asks you to press the button on the meter. On a kWh meter, press the Wi-Fi button for 1 to 3 seconds. You have 60 seconds. When the button press works, the tool prints a line with the token. Paste this line into the `[METER:...]` section of `config.ini`.

    A second pairing with the same name makes the old token invalid. If you pair the same meter from another GX device, pass a different name with `--name`.

    The `--insecure` option turns off the TLS certificate test. If you have no other option, use it as a last resort. See [TLS and VerifyTls](#tls-and-verifytls).


## Configuration

If this is your first install, copy `config.sample.ini` to `config.ini` in the driver folder. Then change the values as you need them. Git ignores `config.ini`, and the release zip has no `config.ini`, so an update does not overwrite it.

```bash
cp /data/etc/dbus-homewizard/config.sample.ini /data/etc/dbus-homewizard/config.ini
nano /data/etc/dbus-homewizard/config.ini
```

The file has one `[DEFAULT]` section and one section for each meter. The section name of a meter starts with `METER:`, for example `[METER:heatpump]`. The name after the colon labels the meter in the log. The driver uses the serial of the meter for every stored value.

For a flag, use `1`, `true`, `yes`, or `on` for yes. Use `0`, `false`, `no`, or `off` for no.

### [DEFAULT]

| Key | Meaning | Default |
|---|---|---|
| `SignOfLifeLog` | Minutes between sign-of-life log lines. | `10` |
| `PollIntervalSeconds` | Seconds between two polls of a meter. The value must be greater than 0. | `1` |
| `OfflineTimeoutSeconds` | Seconds without a new measurement before the driver shows the meter as offline. Empty means 5 for a kWh meter and 15 for a P1 Meter. | empty |

### [METER:&lt;name&gt;]

| Key | Meaning | Default |
|---|---|---|
| `Host` | IP address or host name of the meter. Required. | none (required) |
| `Token` | API token from `pair.py`. 32 hex characters. Required. | none (required) |
| `Role` | First role of the meter. After the first start, the role that you set on the GX screen applies. See [Roles](#roles). | `acload` for a kWh meter, `grid` for a P1 Meter |
| `DeviceInstance` | Device instance number on D-Bus. Each meter needs its own number. | 40 plus the index of the section, so 40 for the first meter and 41 for the second |
| `CustomName` | First name of the meter. After the first start, the name that you set on the GX screen applies. | empty |
| `Phase` | Phase of a 1-phase kWh meter: `L1`, `L2`, or `L3`. The driver puts the values on this phase. | `L1` |
| `Reverse` | If the meter is wired the other way round, set `1`. The driver then swaps import and export, and it flips the sign of the power. | `0` |
| `Position` | Place of a PV inverter or a genset in the system: `0` is AC input, `1` is AC output, and `2` is AC input 2. Stored after the first start, and changeable on the GX screen. | `0` |
| `PollIntervalSeconds` | Seconds between two polls of this meter. Overrides `[DEFAULT]`. | `1` |
| `OfflineTimeoutSeconds` | Seconds without a new measurement before the driver shows this meter as offline. Overrides `[DEFAULT]`. | see `[DEFAULT]` |
| `VerifyTls` | Set `0` to turn off the TLS certificate test for this meter. See [TLS and VerifyTls](#tls-and-verifytls). | `1` |

The driver stores the role, the device instance, the custom name, and the position in the localsettings service of the GX device. The `config.ini` file gives only the first value of each. After that, the values that you set on the GX screen apply. A change in `config.ini` does not change them.


## Roles

You choose the role of each meter on the GX screen, as you do for a Victron energy meter. The role sets the service type and the place of the meter in the GX device list and in VRM.

| Product | Allowed roles |
|---|---|
| `HWE-P1` | `grid` |
| `HWE-KWH1`, `HWE-KWH3`, `SDM230-wifi`, `SDM630-wifi` | `grid`, `pvinverter`, `genset`, `acload`, `heatpump`, `evcharger` |

When you change the role on the GX screen, the driver stores the new role and keeps the same device instance. Then the driver restarts. The meter returns with the new role after a few seconds. Data from the other meters also stops for these seconds. To go back to the old role, change it on the GX screen again.

If the SmartEVSE bridge (dbus-smartevse) already shows the same charger, the `evcharger` role counts the energy twice. Use the `evcharger` role only for a kWh meter on a charger that has no driver of its own. If the driver finds another `com.victronenergy.evcharger` service on D-Bus at startup, it writes a warning to the log.

The heat pump role (`heatpump`) gives the meter its own consumption forecast in Dynamic ESS. The driver uses the `com.victronenergy.heatpump` service type for this role. The owner has not yet tested the minimum Venus OS version for this role on a GX device.

### Sign convention

Power is positive for import on the grid side of the meter. Energy import is energy that the grid gives to the meter. Energy export is energy that the meter gives to the grid.

- For the `pvinverter` and `genset` roles, the driver flips the sign of the power. It also swaps energy import and energy export. Victron expects a positive power for production in these roles.
- For `Reverse = 1`, the driver flips the sign again, and it swaps import and export again. A meter that is wired the other way round gets the right values this way.

The owner has not yet tested this sign convention on a GX device.

The energy totals only go up. The driver publishes the totals of the meter as they are. If the imported energy total goes down, the driver writes a warning to the log and publishes the new value anyway.


## Offline behavior

The driver runs a timer every second. If a meter gives no new measurement for `OfflineTimeoutSeconds`, the driver counts it as offline.

- A kWh meter gives a new measurement with each answer.
- When a P1 Meter loses the link to the smart meter, it answers with its last values. If its `timestamp` changes, the driver counts the measurement as new.

When a meter is offline, the driver sets `/Connected` to 0 and empties the measurement paths. Dynamic ESS then sees that the meter is gone. When new data arrives, the driver sets `/Connected` to 1 again. The service stays on D-Bus, and the role and the device instance do not change.

The default timeouts are 5 seconds for a kWh meter and 15 seconds for a P1 Meter. Older smart meters (DSMR 4) send a reading only every 10 seconds, so the P1 timeout is longer.


## TLS and VerifyTls

If the HomeWizard CA certificate in the `ext` folder signed the certificate of the meter, the driver accepts it. The host name in the certificate must also match `appliance/<cert type>/<serial>`.

If the TLS certificate test fails on the GX device, the driver does not connect to the meter. The log then shows the TLS error. The fallback is `VerifyTls = 0` in the section of that meter. The driver then skips the certificate test for this meter.

If you have no other option, set `VerifyTls = 0`. Then another device on your network can pretend to be the meter. It can send false values, and it can receive the token of the meter. Keep the meter on a network that you trust.

The owner has not yet tested the TLS certificate test on a GX device.


## Install / Update

1. Log in to the GX device with SSH as root. See [Venus OS: Root Access](https://www.victronenergy.com/live/ccgx:root_access#root_access) for details.

2. Download the latest release into `/tmp`. The owner of the repository replaces `<owner>/<repo>` with the real GitHub path first.

    ```bash
    wget -O /tmp/dbus-homewizard.zip https://github.com/<owner>/<repo>/releases/latest/download/dbus-homewizard.zip
    ```

3. Unzip the file into `/data/etc`. The zip has a top folder named `dbus-homewizard`, so the files go to `/data/etc/dbus-homewizard`. The zip has no `config.ini`, so an update keeps yours.

    ```bash
    unzip -o /tmp/dbus-homewizard.zip -d /data/etc
    ```

4. On the first install only, copy `config.sample.ini` to `config.ini`. Then edit `config.ini`, and add the token of each meter from `pair.py`. An update keeps your `config.ini`.

    ```bash
    cp /data/etc/dbus-homewizard/config.sample.ini /data/etc/dbus-homewizard/config.ini
    nano /data/etc/dbus-homewizard/config.ini
    ```

5. Run `install.sh`.

    ```bash
    bash /data/etc/dbus-homewizard/install.sh
    ```

    The script sets the file permissions and creates the service link `/service/dbus-homewizard`. It also adds itself to `/data/rc.local`, so the driver survives a firmware update. Daemontools starts the service within seconds.

If you update an existing install, run `bash /data/etc/dbus-homewizard/restart.sh` after step 3.


## Uninstall

Run this command:

```bash
bash /data/etc/dbus-homewizard/uninstall.sh
```

The script removes the line from `/data/rc.local`, stops the service, and removes the service link. Then it asks you a question: delete the driver files and `config.ini`, yes or no? Reboot the device after you uninstall.


## Restart

Run this command:

```bash
bash /data/etc/dbus-homewizard/restart.sh
```

The script kills the Python process. Daemontools then starts it again.


## Debugging

To read the log, run this command:

```bash
tail -n 100 -F /data/log/dbus-homewizard/current | tai64nlocal
```

To see the service status, run this command:

```bash
svstat /service/dbus-homewizard
```

The output looks like `/service/dbus-homewizard: up (pid 5845) 185 seconds`. If the driver cannot start, it logs the cause, waits 60 seconds, and stops. Daemontools then starts it again. If the seconds never go above 60, the driver fails at each start. Read the log to find the cause.

If the setup of one meter fails, the log shows `setup failed` and `the driver restarts in 60 seconds`. The other meters keep running until the restart.

If the log shows `invalid config file`, look at the values in `config.ini`. The message names the key and the section.

If the log shows `the token is not valid. Run pair.py <host> to get a new token.`, run `pair.py` again, and paste the new token into `config.ini`. Then restart the driver.

If you see nothing in the log, raise the log level. In `/data/etc/dbus-homewizard/dbus-homewizard.py`, change `level=logging.WARNING` to `level=logging.INFO` or `level=logging.DEBUG`. Then restart the driver.


## Compatibility

The target version is Venus OS v3.85. The owner has not yet tested the driver on a GX device. The owner adds the tested versions here.

The driver needs Python 3.8 or newer. It uses only the standard library of Python, plus the `velib_python` files and the `dbus` and `GLib` modules of the GX device. The tests also run on Python 3.12.


## Versioning

The project uses [semVersie](https://github.com/RonaldPhilipsen/semVersie) to choose a version number for each release. semVersie reads the titles of the merged pull requests. It does not read the code.

Each pull request title must follow the [conventional commits](https://www.conventionalcommits.org/) format:

- `fix: ...` raises the patch number (1.2.3 becomes 1.2.4).
- `feat: ...` raises the minor number (1.2.3 becomes 1.3.0).
- `feat!: ...` marks a breaking change. It raises the major number (1.2.3 becomes 2.0.0).

When a pull request merges into `main`, a GitHub workflow builds `dbus-homewizard.zip` and publishes it as a release. The version shows on the GX device in the `/Mgmt/ProcessVersion` path, together with the Python version. A copy of the code that is not from a release shows `0.0.0-dev`.
