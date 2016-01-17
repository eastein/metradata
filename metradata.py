from __future__ import absolute_import
import tornado.web
import tornado.gen
import tornado.ioloop
import json
import metraapi.metra
import metraapi.metranado
import pytz
import datetime

import inspect
import os


import logging
logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', filename='metradata.log', level=logging.DEBUG)


class JSONHandler(tornado.web.RequestHandler):

    def wj(self, status, j):
        self.application.__io_instance__.add_callback(lambda: self._wj(status, j))

    def _wj(self, status, j):
        self.set_status(status)
        self.set_header('Content-Type', 'application/json')
        self.set_header('Cache-Control', 'no-cache')
        self.write(j)
        self.finish()


metra = metraapi.metra.Metra()

# TODO add a general exception handler


class Lines(JSONHandler):

    @tornado.web.asynchronous
    def get(self):
        self._wj(200, json.dumps({'data': dict([(l.id, l.todict()) for l in list(metra.lines.values())])}))


class Stations(JSONHandler):

    @tornado.gen.coroutine
    def get(self, line_id):
        line = None
        try:
            line = metra.line(line_id)
        except metraapi.metra.InvalidLineException:
            self._wj(404, json.dumps({'status': 'error', 'message': 'No such line %s' % line_id}))
            return

        stations = yield metraapi.metranado.get_stations_from_line(line_id)

        self._wj(200, json.dumps({'data': [[s['id'], s['name']] for s in stations]}))


class Station(JSONHandler):

    @tornado.web.asynchronous
    def get(self, line_id, station_id):
        line = None
        try:
            line = metra.line(line_id)
        except metraapi.metra.InvalidLineException:
            self._wj(404, json.dumps({'status': 'error', 'message': 'No such line %s' % line_id}))
            return

        station = None
        try:
            station = line.station(station_id)
        except metraapi.metra.InvalidStationException:
            self._wj(404, json.dumps({
                'status': 'error',
                'message': 'No such station %s on line %s' % (station_id, line_id)
            }))
            return

        station_body = {
            'station': {
                'id': station.id,
                'name': station.name,
                'line_id': station.line_id,
                'fare_zone': station.fare_zone,
                'bike_parking': station.bike_parking,
                'wheelchair_boarding': station.wheelchair_boarding,
                'location': station.location,
                'url': station.url
            }
        }

        self._wj(200, json.dumps(station_body))
        return


def non_naive_dt_to_unixts(dt):
    return (dt.astimezone(pytz.utc) - pytz.utc.localize(datetime.datetime(1970, 1, 1, 0, 0, 0))).total_seconds()


class Runs(JSONHandler):

    @tornado.web.asynchronous
    def get(self, line_id, dpt_station_id, arv_station_id):
        try:
            line = metra.line(line_id)
            dpt = line.station(dpt_station_id)
            arv = line.station(arv_station_id)

            time_format = "%H:%M"

            runs = dpt.runs_to(arv)
            runs_output = list()
            for run in runs:
                r = {
                    'line_id': run.line.id,
                    'dpt_station_id': run.dpt_station.id,
                    'arv_station_id': run.arv_station.id,
                    'train_number': run.train_number,
                    'en_route': run.en_route,
                    'gps': run.gps,
                    'on_time': run.on_time,
                    'state': run.state,
                    'as_of_unixts': non_naive_dt_to_unixts(run.as_of),
                    'as_of_time': run.as_of.strftime(time_format)
                }
                for tt in ['estimated', 'scheduled']:
                    for end in ['dpt', 'arv']:
                        dt = getattr(run, '%s_%s_time' % (tt, end))
                        if dt is not None:
                            r['%s_%s_unixts' % (tt, end)] = non_naive_dt_to_unixts(dt)
                            r['%s_%s_time' % (tt, end)] = dt.strftime(time_format)
                if 'md_user_id' in self.cookies:
                    logging.debug('run_trace %s %s %s for user_id=%s - data %s' % (line_id, dpt_station_id, arv_station_id,
                                                                                   self.cookies['md_user_id'].value, ','.join(['%s=%s' % (k, repr(v)) for (k, v) in list(r.items())])))
                runs_output.append(r)

            self._wj(200, json.dumps({'data': runs_output}))
        except metraapi.metra.InvalidLineException:
            self._wj(404, json.dumps({'status': 'error', 'message': 'No such line %s' % line_id}))
            return
        except metraapi.metra.InvalidStationException:
            self._wj(404, json.dumps({'status': 'error', 'message': 'No such station.'}))
            return

STATIC_PATH = os.path.join(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))), 'static')
INTERFACE_PATH = os.path.join(STATIC_PATH, 'index.html')
INTERFACE_HTML = open(INTERFACE_PATH).read()


class InterfaceHandler(tornado.web.RequestHandler):

    def get(self):
        self.write(open(INTERFACE_PATH).read())

HANDLER_SET = [
    (r"/api/metra$", Lines),
    (r"/api/metra/([\-A-Z]+)$", Stations),
    (r"/api/metra/([\-A-Z]+)/([\-A-Z]+)$", Station),
    (r"/api/metra/([\-A-Z]+)/([\.\-A-Z0-9]+)/([\.\-A-Z0-9]+)$", Runs),
    (r"/static/(.*)$", tornado.web.StaticFileHandler, {'path': STATIC_PATH}),
    (r"/$", InterfaceHandler),
]

if __name__ == '__main__':
    application = tornado.web.Application(HANDLER_SET)

    application.listen(8089)

    application.__io_instance__ = tornado.ioloop.IOLoop.instance()
    application.__io_instance__.start()
