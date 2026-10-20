# ZHA quirk for Tuya `TS0601` / `_TZE284_hodyryli`

A custom [ZHA](https://www.home-assistant.io/integrations/zha/) quirk for a Tuya
Zigbee temperature and humidity sensor with an **external wired probe** and an
**LCD clock**.

| | |
|---|---|
| Zigbee model | `TS0601` |
| Zigbee manufacturer | `_TZE284_hodyryli` |
| Marked on the case | ZT08 |
| Also sold/listed as | "ZY-ZTH03PRO" (reportedly a different device, so go by the manufacturer string) |

Without a quirk, ZHA pairs the device as a generic Tuya `TS0601` with no useful
entities. This quirk maps the device's Tuya datapoints onto standard Home
Assistant entities.

The same documentation is included in the docstring at the top of the quirk
file, so it stays with the file if you copy it on its own.

## Features

- Internal temperature (°C), with correct handling of readings below 0 °C
- Humidity (%)
- Battery level (mapped from the device's 3-step battery state)
- External probe temperature (°C) as a separate sensor, with long-term statistics enabled
- LCD clock sync fix, so the on-device clock shows the time instead of dashes

## Entities

| Entity | Source | Notes |
|---|---|---|
| Temperature | DP 1 | Standard temperature sensor |
| Humidity | DP 2 | Standard humidity sensor |
| Battery | DP 3 | Reports 10 %, 50 % or 100 % only |
| External Temperature | DP 38 | State class `measurement`, so it gets long-term statistics |

### Datapoint map

| DP | Meaning | Type | Conversion |
|---|---|---|---|
| 1 | Internal temperature | value | signed 16-bit, ÷ 10 |
| 2 | Humidity | value | raw whole percent |
| 3 | Battery state | enum | 0 / 1 / 2 → 10 % / 50 % / 100 % |
| 17 | LCD clock commit | bool | written as `false` ~500 ms after each time sync |
| 38 | External probe temperature | value | signed 16-bit, ÷ 10 |

## Requirements

- Home Assistant with the ZHA integration (the quirk uses the `TuyaQuirkBuilder`
  API from `zha-device-handlers`, so a reasonably recent Home Assistant is needed)
- Access to your Home Assistant `/config` folder

## Installation

1. Copy `ts0601_tze284_hodyryli.py` to a folder in your config, for example:

   ```
   /config/custom_zha_quirks/ts0601_tze284_hodyryli.py
   ```

2. Point ZHA at that folder in `configuration.yaml`:

   ```yaml
   zha:
     custom_quirks_path: /config/custom_zha_quirks/
   ```

3. Restart Home Assistant.

4. Remove the device from ZHA and pair it again, or re-interview it, so ZHA
   applies the quirk. Wake the device by pressing the button on top while pairing.

## Verifying the installation

- **Quirk loaded:** open the device page, choose **⋮ → Zigbee device info**, and
  check that the quirk name is shown instead of a bare `TS0601`.
- **Entities:** the device should show temperature, humidity, battery and an
  "External Temperature" sensor.
- **State class:** in **Developer Tools → States**, open the external temperature
  entity and check for `state_class: measurement`.
- **Statistics:** in **Developer Tools → Statistics**, the external temperature
  sensor should be listed. Data can take an hour or two to appear because the
  device reports infrequently.
- **Clock sync (optional):** enable debug logging and look for
  `Committing LCD clock: DP 17 = False` after the device wakes:

  ```yaml
  logger:
    default: warning
    logs:
      zhaquirks: debug
  ```

## How it works

- **Humidity scaling.** Home Assistant's ZCL humidity attribute is stored in
  0.01 % units. The device sends whole percent (e.g. `51`), so the quirk
  multiplies by 100. A scale of 1 shows 51 % as 0.5 %.
- **Signed temperatures.** Temperature datapoints are decoded from the low
  16 bits as a signed value, so freezing temperatures don't appear as huge
  positive numbers. Positive readings are unaffected.
- **Battery.** The device only reports a 3-step state, which is mapped to
  10 / 50 / 100 % and converted to ZCL half-percent units.
- **Clock sync.** The device requests the time (Tuya cluster command `0x24`). ZHA
  answers with a Unix-1970 timestamp, which this device expects, but the MCU only
  applies the time after a follow-up write of DP 17 = `false`. `ZT08MCUCluster`
  sends that write about 500 ms after each time request.

## Known limitations

- **Infrequent reports.** The device can go more than an hour between temperature
  and humidity reports. The interval is set by the device firmware. These Tuya
  MCU devices ignore standard ZCL reporting configuration, which is why the
  quirk uses `skip_configuration()`. No interval or sensitivity datapoint has
  been identified for this model.
- **Sleepy device.** It only talks when it wakes up, so values don't update on
  demand. Pressing the button on top forces a report.
- **24-hour clock.** DP 17 is also the clock's time-format setting, so the commit
  write forces 24-hour format. There is no 12-hour option in this quirk.
- **Clock timezone.** The displayed time follows the timezone of the Home
  Assistant process. On Docker or Core installs this may be UTC, in which case
  set the `TZ` environment variable.
- **Short window for the clock write.** The commit write goes to a battery
  device, so if it goes back to sleep within that half second the clock may not
  update until a later wake-up.

## Status

| Feature | Status |
|---|---|
| Temperature and humidity | Verified on a real device |
| `measurement` state class on the external probe | Confirmed working |
| LCD clock sync fix | Based on zigbee2mqtt findings for this device, not yet confirmed here |
| Negative-temperature decoding | Based on zigbee2mqtt findings for this device, not yet confirmed here |

Reports from other hardware revisions are welcome.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| Device still shows no entities | Quirk not applied. Check `custom_quirks_path`, restart Home Assistant, then remove and re-pair the device. |
| Quirk fails to load with an import error on `SensorStateClass` | The import location can differ between versions. The path used in the file works on a confirmed setup. If yours differs, update Home Assistant, or remove the `state_class` argument and the import to run without long-term statistics. |
| Humidity shows about 0.5 % | Old file still loaded. Make sure `.tuya_humidity(dp_id=2, scale=100)` is in the file and restart. |
| `state_class` missing on the external probe | Reload the ZHA integration or re-interview the device. |
| Clock shows dashes | Wake the device with its button, check the debug log line above, and check the timezone of the Home Assistant process. |
| Clock shows the wrong hour | Timezone of the Home Assistant process, see limitations above. |

## Prompt log

This quirk was developed iteratively with an AI assistant. These are all the
prompts given, in order and as written (assistant replies omitted), to keep
track of how the project evolved. Every change adds its prompt here.

1. > please create code for home assistant custom quirk for "TS0601" "_TZE284_hodyryli" device
2. > humidity is shown 0.5% in home assistant, while on screen I see 51%. Please correct the code correspondingly.
3. > Script works fine, but readings of temperature are infrequent, sometimes once in more than 1 hour. Can you increase reading frequency somehow? Does this device has some special clock synchronization that impact reading frequency?
4. > yes, please add the clock-sync fix
5. > Are there any other known fixes possible for this device?
6. > apply 1,2 and 4 only. I'll deal with interval and sensitivity later.
7. > how can I check in Home Assistant your change of state_class to MEASUREMENT?
8. > Please provide github-friendly final version of code and its documentation in MD format.
9. > 1) Please add MIT license  
   > 2) measurement state class confirmed, temp & humidity verified. Ok.  
   > 3) Please revert back adding docs into the code. I want documentation to be duplicated in the code.
10. > please create zip file for outputs, because executable are not allowed for download
11. > also, please update documentation with all prompts I gave you, without your answers. I'd like to keep track of prompts. Make a new section in docs. Update zip correspondingly. Do so for any change next time.

Prompt 9 was sent together with three attached excerpts of earlier assistant
replies, which are not reproduced here.

## Credits

- Datapoint map and clock-sync behavior based on the zigbee2mqtt
  external-converter work for this device.
- Built on `TuyaQuirkBuilder` from
  [zha-device-handlers](https://github.com/zigpy/zha-device-handlers).

## License

MIT. See [LICENSE](LICENSE).
