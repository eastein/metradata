import tornado.web
import tornado.ioloop
import json
import metraapi.metra
import pytz, datetime

class JSONHandler(tornado.web.RequestHandler):
    def wj(self, status, j) :
        self.application.__io_instance__.add_callback(lambda: self._wj(status, j))

    def _wj(self, status, j) :
        self.set_status(status)
        self.set_header('Access-Control-Allow-Origin', '*')
        self.set_header('Cache-Control', 'no-cache')
        self.set_header('Content-Type', 'application/json')
        self.write(j)
        self.finish()


metra = metraapi.metra.Metra()

# TODO add a general exception handler

class Lines(JSONHandler):
    @tornado.web.asynchronous
    def get(self) :
        self._wj(200, json.dumps({'data': dict([(l.id, l.name) for l in metra.lines.values()])}))

class Stations(JSONHandler):
    @tornado.web.asynchronous
    def get(self, line_id) :
        line = None
        try :
            line = metra.line(line_id)
        except metraapi.metra.InvalidLineException :
            self._wj(404, json.dumps({'status' : 'error', 'message' : 'No such line %s' % line_id}))
            return

        self._wj(200, json.dumps({'data': [[s.id, s.name] for s in line.stations]}))

def non_naive_dt_to_unixts(dt):
    return (dt.astimezone(pytz.utc) - pytz.utc.localize(datetime.datetime(1970, 1, 1, 0, 0, 0))).total_seconds()

class Runs(JSONHandler):
    @tornado.web.asynchronous
    def get(self, line_id, dpt_station_id, arv_station_id):
        try:
            line = metra.line(line_id)
            dpt = line.station(dpt_station_id)
            arv = line.station(arv_station_id)

            runs = dpt.runs_to(arv)
            runs_output = list()
            for run in runs :
                r = {
                    'line_id' : run.line.id,
                    'dpt_station_id' : run.dpt_station.id,
                    'arv_station_id' : run.arv_station.id,
                    'train_number': run.train_number,
                    'en_route': run.en_route,
                    'gps': run.gps,
                    'on_time': run.on_time,
                    'state': run.state,
                    'as_of_unixts': non_naive_dt_to_unixts(run.as_of)
                }
                for tt in ['estimated', 'scheduled'] :
                    for end in ['dpt', 'arv'] :
                        dt = getattr(run, '%s_%s_time' % (tt, end))
                        if dt is not None :
                            r['%s_%s_unixts' % (tt, end)] = non_naive_dt_to_unixts(dt)
                            r['%s_%s_time'   % (tt, end)] = dt.strftime('%H:%M:%S')
                runs_output.append(r)

            self._wj(200, json.dumps({'data': runs_output}))
        except metraapi.metra.InvalidLineException :
            self._wj(404, json.dumps({'status' : 'error', 'message' : 'No such line %s' % line_id}))
            return
        except metraapi.metra.InvalidStationException :
            self._wj(404, json.dumps({'status' : 'error', 'message' : 'No such station.'}))
            return

HANDLER_SET = [
    (r"/api/metra$", Lines),
    (r"/api/metra/([\-A-Z]+)$", Stations),
    (r"/api/metra/([\-A-Z]+)/([\.\-A-Z]+)/([\.\-A-Z]+)", Runs),
]

if __name__ == '__main__' :
    application = tornado.web.Application(HANDLER_SET)

    application.listen(8089)

    application.__io_instance__ = tornado.ioloop.IOLoop.instance()
    application.__io_instance__.start()
