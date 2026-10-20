"""ZHA quirk for Tuya TS0601 _TZE284_hodyryli (marked ZT08 on the case).

Temperature & humidity sensor with an external wired probe and an LCD clock.
(Some listings call it ZY-ZTH03PRO, but that is reportedly a different device.)

Datapoint map (confirmed working, ported from the zigbee2mqtt external
converter for this manufacturer/model pair):
    DP 1  -> internal temperature, value / 10   (°C)
    DP 2  -> humidity, raw value                (%)
    DP 3  -> battery state, enum 0/1/2 -> 10/50/100 %
    DP 38 -> external probe temperature, value / 10 (°C)

Both temperature DPs are decoded as signed 16-bit values (low 16 bits,
sign-extended), so readings below 0 °C don't show up as huge positive numbers.

LCD clock:
    The MCU requests the time (cluster command 0x24). ZHA replies with raw
    Unix-1970 seconds (UTC + local). The MCU only applies it if DP 17 = false
    is written ~500 ms afterwards, which ZT08MCUCluster below does. The
    displayed time follows the timezone of the Home Assistant process.

Entities:
    Temperature           DP 1   standard temperature sensor
    Humidity              DP 2   standard humidity sensor
    Battery               DP 3   reports 10 %, 50 % or 100 % only
    External Temperature  DP 38  state class "measurement", so Home Assistant
                                 records long-term statistics for it

Requirements:
    Home Assistant with the ZHA integration (recent enough to provide the
    TuyaQuirkBuilder API from zha-device-handlers) and access to /config.

Installation:
    1. Copy this file to a folder in your config, for example:
           /config/custom_zha_quirks/ts0601_tze284_hodyryli.py
    2. Point ZHA at that folder in configuration.yaml:
           zha:
             custom_quirks_path: /config/custom_zha_quirks/
    3. Restart Home Assistant.
    4. Remove the device from ZHA and pair it again (or re-interview it) so
       the quirk is applied. Wake the device with the button on top while
       pairing.

Verifying the installation:
    - Device page -> "Zigbee device info" shows the quirk name instead of a
      bare TS0601.
    - Developer Tools -> States: the external temperature entity has
      state_class: measurement.
    - Developer Tools -> Statistics: the external temperature sensor is
      listed (data can take an hour or two to appear).
    - Clock sync: with debug logging enabled for zhaquirks, the line
      "Committing LCD clock: DP 17 = False" appears after the device wakes:
           logger:
             default: warning
             logs:
               zhaquirks: debug

How it works:
    - Humidity: the ZCL humidity attribute is stored in 0.01 % units, the
      device sends whole percent (e.g. 51), so the quirk multiplies by 100.
      A scale of 1 shows 51 % as 0.5 %.
    - Temperatures: decoded from the low 16 bits as a signed value, so
      readings below 0 C are not shown as huge positive numbers.
    - Battery: the device only reports a 3-step state, mapped to 10/50/100 %
      and converted to ZCL half-percent units.
    - Clock: see "LCD clock" above.

Known limitations:
    - Infrequent reports: the device can go more than an hour between
      temperature and humidity reports. The interval is set by the device
      firmware. Tuya MCU devices ignore standard ZCL reporting configuration,
      which is why the quirk uses skip_configuration(). No interval or
      sensitivity datapoint has been identified for this model.
    - Sleepy device: it only talks when it wakes up. Pressing the button on
      top forces a report.
    - 24-hour clock: DP 17 is also the clock's time-format setting, so the
      commit write forces 24-hour format.
    - Clock timezone: follows the timezone of the Home Assistant process. On
      Docker or Core installs this may be UTC; set the TZ environment
      variable if the clock is off by hours.
    - The clock commit write goes to a battery device; if it goes back to
      sleep within that half second, the clock may not update until a later
      wake-up.

Status:
    - Temperature and humidity: verified on a real device.
    - "measurement" state class on the external probe: confirmed working.
    - LCD clock sync fix: based on zigbee2mqtt findings for this device,
      not yet confirmed.
    - Negative-temperature decoding: based on zigbee2mqtt findings for this
      device, not yet confirmed.

Troubleshooting:
    - No entities after pairing: the quirk was not applied. Check
      custom_quirks_path, restart Home Assistant, remove and re-pair.
    - Import error on SensorStateClass: the import location can differ
      between versions. If yours differs, update Home Assistant, or remove
      the state_class argument and the import to run without long-term
      statistics.
    - Humidity shows about 0.5 %: an old file is still loaded; make sure
      .tuya_humidity(dp_id=2, scale=100) is in the file and restart.
    - state_class missing on the external probe: reload the ZHA integration
      or re-interview the device.
    - Clock shows dashes: wake the device with its button, check the debug
      log line above and the timezone of the Home Assistant process.

Prompt log:
    This quirk was developed iteratively with an AI assistant. These are all
    the prompts given, in order and as written (assistant replies omitted),
    to keep track of how the project evolved. Every change adds its prompt
    here.
    1. please create code for home assistant custom quirk for "TS0601"
       "_TZE284_hodyryli" device
    2. humidity is shown 0.5% in home assistant, while on screen I see 51%.
       Please correct the code correspondingly.
    3. Script works fine, but readings of temperature are infrequent,
       sometimes once in more than 1 hour. Can you increase reading
       frequency somehow? Does this device has some special clock
       synchronization that impact reading frequency?
    4. yes, please add the clock-sync fix
    5. Are there any other known fixes possible for this device?
    6. apply 1,2 and 4 only. I'll deal with interval and sensitivity later.
    7. how can I check in Home Assistant your change of state_class to
       MEASUREMENT?
    8. Please provide github-friendly final version of code and its
       documentation in MD format.
    9. 1) Please add MIT license
       2) measurement state class confirmed, temp & humidity verified. Ok.
       3) Please revert back adding docs into the code. I want
       documentation to be duplicated in the code.
    10. please create zip file for outputs, because executable are not
        allowed for download
    11. also, please update documentation with all prompts I gave you,
        without your answers. I'd like to keep track of prompts. Make a new
        section in docs. Update zip correspondingly. Do so for any change
        next time.
    Prompt 9 was sent together with three attached excerpts of earlier
    assistant replies, which are not reproduced here.

Credits:
    Datapoint map and clock-sync behavior are based on the zigbee2mqtt
    external-converter work for this device. Built on TuyaQuirkBuilder from
    zha-device-handlers (https://github.com/zigpy/zha-device-handlers).

License: MIT (see LICENSE).
"""

import asyncio

import zigpy.types as t
from zigpy.zcl.clusters.general import PowerConfiguration

from zhaquirks.tuya import (
    TUYA_CLUSTER_ID,
    TuyaCommand,
    TuyaDatapointData,
    TuyaPowerConfigurationCluster,
)
from zhaquirks.tuya.builder import TuyaQuirkBuilder, TuyaTemperatureMeasurement
from zhaquirks.tuya.mcu import TuyaMCUCluster
from zigpy.quirks.v2.homeassistant import UnitOfTemperature
from zigpy.quirks.v2.homeassistant.sensor import SensorDeviceClass, SensorStateClass


class ZT08MCUCluster(TuyaMCUCluster):
    """Tuya MCU cluster with LCD clock commit for the ZT08.

    ZHA's default time sync already answers the device's time request (0x24)
    with raw Unix-1970 seconds (UTC + local), which is what this MCU expects.
    But the MCU silently ignores the new time unless a DP 17 = false write
    follows ~500 ms later, so the LCD clock stays at 00:xx / dashes.
    """

    def handle_set_time_request(self, payload):
        """Answer the time request, then commit the time onto the LCD."""
        status = super().handle_set_time_request(payload)
        self.create_catching_task(self._commit_lcd_clock())
        return status

    async def _commit_lcd_clock(self) -> None:
        """Write DP 17 = false shortly after the time sync."""
        await asyncio.sleep(0.5)
        command = TuyaCommand(
            status=0,
            tsn=self.endpoint.device.application.get_sequence(),
            datapoints=[TuyaDatapointData(17, False)],
        )
        self.debug("Committing LCD clock: DP 17 = False")
        await self.command(self.mcu_write_command, command, expect_reply=False)


def _signed16(value: int) -> int:
    """Sign-extend the low 16 bits of a Tuya VALUE datapoint.

    The device sends temperatures as 4-byte values where negative readings
    may arrive as 0x0000FF9C or 0xFFFFFF9C. Taking the low 16 bits as signed
    handles both; positive readings are unchanged.
    """
    value &= 0xFFFF
    return value - 0x10000 if value > 0x7FFF else value


def _battery_state_to_percentage(value: int) -> int:
    """Map Tuya battery-state enum (0/1/2) to ZCL battery_percentage_remaining.

    ZCL battery_percentage_remaining is reported in half-percent units,
    so 100% must be sent as 200.
    """
    mapping = {0: 10, 1: 50, 2: 100}
    return mapping.get(value, 0) * 2


(
    TuyaQuirkBuilder("_TZE284_hodyryli", "TS0601")
    # Internal temperature sensor (DP 1, /10 °C, signed) -> standard HA
    # temperature entity. Equivalent to tuya_temperature(scale=10) but with
    # sign handling; ZCL stores centidegrees, so decidegrees * 10.
    .tuya_dp(
        dp_id=1,
        ep_attribute=TuyaTemperatureMeasurement.ep_attribute,
        attribute_name="measured_value",
        converter=lambda x: _signed16(x) * 10,
    )
    .adds(TuyaTemperatureMeasurement)
    # Humidity sensor (DP 2, raw whole-percent value from device) -> standard
    # HA humidity entity. ZCL RelativeHumidity.measured_value is stored in
    # 0.01% units, so a raw reading of 51 (meaning 51%) needs scale=100 to
    # store 5100 (=51.00%). scale=1 previously stored 51 (=0.51%), which
    # rounded to the wrong 0.5% shown in HA.
    .tuya_humidity(dp_id=2, scale=100)
    # Battery state enum (DP 3) -> mapped onto the PowerConfiguration cluster
    # so it shows up as a normal HA battery entity
    .tuya_dp(
        dp_id=3,
        ep_attribute=PowerConfiguration.ep_attribute,
        attribute_name=PowerConfiguration.AttributeDefs.battery_percentage_remaining.name,
        converter=_battery_state_to_percentage,
    )
    .adds(TuyaPowerConfigurationCluster)
    # External probe temperature (DP 38 / 0x26, /10 °C, signed) -> exposed as
    # its own sensor entity on the Tuya manufacturer-specific cluster
    .tuya_dp_attribute(
        dp_id=38,
        attribute_name="external_temperature",
        type=t.int16s,
        converter=_signed16,
    )
    .sensor(
        attribute_name="external_temperature",
        cluster_id=TUYA_CLUSTER_ID,
        divisor=10,
        multiplier=1,
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        # MEASUREMENT lets HA record long-term statistics for this sensor
        state_class=SensorStateClass.MEASUREMENT,
        translation_key="external_temperature",
        fallback_name="External Temperature",
    )
    # Tuya EF00 devices don't support standard ZCL attribute reporting config
    .skip_configuration()
    .add_to_registry(replacement_cluster=ZT08MCUCluster)
)
