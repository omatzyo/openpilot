#!/usr/bin/env python3
from cereal import log, messaging
from laika import AstroDog
from laika.gps_time import GPSTime
from laika.helpers import ConstellationId
from laika.ephemeris import convert_ublox_ephem
from laika.raw_gnss import GNSSMeasurement, calc_pos_fix, correct_measurements, process_measurements, read_raw_ublox

time_first_gnss_message = None


def process_ublox_msg(ublox_msg, dog: AstroDog, ublox_mono_time: int, correct=False):
  global time_first_gnss_message
  if ublox_msg.which == 'measurementReport':
    report = ublox_msg.measurementReport
    if len(report.measurements) == 0:
      return None
    new_meas = read_raw_ublox(report)
    if time_first_gnss_message is None:
      time_first_gnss_message = GPSTime(report.gpsWeek, report.rcvTow)
    measurements = process_measurements(new_meas, dog)
    if len(measurements) == 0:
      return None

      # pos fix needs more than 5 processed_measurements
    if correct:
      pos_fix = calc_pos_fix(measurements)[0]
      if len(pos_fix) > 0:
        measurements = correct_measurements(measurements, pos_fix[:3], dog)
    # pos or vel fixes can be an empty list if not enough correct measurements are available
    correct_meas_msgs = [create_measurement_msg(m) for m in measurements]

    dat = messaging.new_message('gnssMeasurements')
    dat.gnssMeasurements = {
      "ubloxMonoTime": ublox_mono_time,
      "correctedMeasurements": correct_meas_msgs
    }
    return dat
  elif ublox_msg.which == 'ephemeris' and time_first_gnss_message is not None:
    ephem = convert_ublox_ephem(ublox_msg.ephemeris, time_first_gnss_message)
    dog.add_ephem(ephem, dog.orbits)
  # elif ublox_msg.which == 'ionoData': # todo add this. Needed to correct messages offline. First fix ublox_msg.cc to sent them.


def create_measurement_msg(meas: GNSSMeasurement):
  c = log.GnssMeasurements.CorrectedMeasurement.new_message()
  c.constellationId = meas.constellation_id.value
  c.svId = int(meas.prn[1:])
  if len(meas.observables_final) > 0:
    observables = meas.observables_final
  else:
    observables = meas.observables

  c.glonassFrequency = meas.glonass_freq if meas.constellation_id == ConstellationId.GLONASS else 0
  c.pseudorange = float(observables['C1C'])
  c.pseudorangeStd = float(meas.observables_std['C1C'])
  c.pseudorangeRate = float(observables['D1C'])
  c.pseudorangeRateStd = float(meas.observables_std['D1C'])
  c.satPos = meas.sat_pos_final.tolist()
  c.satVel = meas.sat_vel.tolist()
  return c


def main():
  dog = AstroDog()
  sm = messaging.SubMaster(['ubloxGnss'])
  pm = messaging.PubMaster(['gnssMeasurements'])

  while True:
    sm.update()

    # Todo if no internet available use latest ephemeris
    if sm.updated['ubloxGnss']:
      ublox_msg = sm['ubloxGnss']
      msg = process_ublox_msg(ublox_msg, dog, sm.logMonoTime['ubloxGnss'])
      if msg is None:
        msg = messaging.new_message('gnssMeasurements')
      pm.send('gnssMeasurements', msg)


if __name__ == "__main__":
  main()
