#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# otelsrv.py: A tiny utility for testing OpenTelemetry/HTTP test
#
# License:
#   Apache License, Version 2.0
#
# History:
#   * 2023/09/03 v0.1 Initial version
#
# Author:
#   Masanori Itoh <masanori.itoh@gmail.com>
#
# Dependencies:
#   See below imports (opentelemetry)
import sys
import time
import datetime
import argparse
import re
#import requests
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer
from http import HTTPStatus
#

tracer = None
args = None

class OtelSrv(BaseHTTPRequestHandler):

    def do_GET(self):
        global tracer
        global args
        self.protocol_version = 'HTTP/1.1'
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', 0)
        self.end_headers()
        self.wfile.write(''.encode('utf-8'))

        if args.print_headers:
            for elm in self.headers:
                print(elm, self.headers[elm])
        return

    def do_POST(self):
        global tracer
        global args

        if args.print_headers:
            for elm in self.headers:
                print(elm, self.headers[elm])

        traceparent = None
        if 'traceparent' in self.headers:
            print('traceparent: %s' % (self.headers['traceparent']))
            traceparent = self.headers['traceparent']
        ctx = None
        if traceparent:
            carrier = {'traceparent': traceparent}
            ctx = TraceContextTextMapPropagator().extract(carrier=carrier)

        if 'Content-Length' in self.headers:
            content_length = int(self.headers['Content-Length'])
        else:
            content_length = 0
        headers = {}

        post_data = self.rfile.read(content_length)
        self.protocol_version = 'HTTP/1.1'
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-Type', 'text/html')
        msg = ('')
        self.send_header('Content-Length', len(msg))
        self.end_headers()
        self.wfile.write(msg.encode('utf-8'))

        span1 = None
        if args.enable_otel:
            span1 = tracer.start_span("do_POST", context=ctx)
            inject(headers)
            if 'traceparent' in headers.keys():
                print(headers['traceparent'])
        if len(post_data) > args.dump_size:
            dump_size = args.dump_size
        else:
            dump_size = len(post_data)
        dump_str = ''
        for i in range(0, dump_size):
            dump_str += '%02x ' % (post_data[i])
            if ((i + 1) % 16) == 0:
                print(dump_str)
                dump_str = ''
        if (dump_size % 16 != 0):
            print(dump_str)
        if args.enable_otel:
            span1.end()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='otelsrv.py')
    parser.add_argument('--endpoint', default=None,
                        help='OTLP Collector Endpoint (e.g. http://localhost:4317)')
    parser.add_argument('--otlp_protocol', default='grpc')
    parser.add_argument('--console', action='store_true')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--bind_address', default='0.0.0.0')
    parser.add_argument('--bind_port', type=int, default=8080)
    parser.add_argument('--dump_size', type=int, default=256)
    parser.add_argument('--enable_otel', action='store_true')
    parser.add_argument('--print_headers', action='store_true')
    args = parser.parse_args()
    #
    # Setup OpenTelemetry
    #
    if args.enable_otel:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.propagate import inject
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter
        if args.otlp_protocol == 'grpc':
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        elif args.otlp_protocol == 'http/protobuf':
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            if not re.match('.+/v1/traces$', args.endpoint):
                args.endpoint += '/v1/traces'
                if args.debug:
                    print('DEBUG: Appending /v1/traces to endpoint.', args.endpoint)
        else:
            print('Unknown otlp_protocol: %s' % (args.otlp_protocol))
            sys.exit()
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
        resource = Resource(attributes={'service.name': sys.argv[0]})
        provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)
        tracer = trace.get_tracer(sys.argv[0])
        if args.endpoint:
            if args.otlp_protocol == 'grpc':
                otlp_exporter = OTLPSpanExporter(endpoint=args.endpoint, insecure=True)
            else:
                otlp_exporter = OTLPSpanExporter(endpoint=args.endpoint)
            otlp_processor = BatchSpanProcessor(otlp_exporter)
            trace.get_tracer_provider().add_span_processor(otlp_processor)
        if args.console:
            console_exporter = ConsoleSpanExporter()
            console_processor = BatchSpanProcessor(console_exporter)
            trace.get_tracer_provider().add_span_processor(console_processor)
    #
    # Create HTTP Server
    #
    httpd = HTTPServer((args.bind_address, args.bind_port), OtelSrv)
    httpd.serve_forever()
