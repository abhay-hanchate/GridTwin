Traceback (most recent call last):
  File "C:\Users\524ta\AppData\Local\Programs\Python\Python313\Lib\site-packages\urllib3\connection.py", line 198, in _new_conn
    sock = connection.create_connection(
        (self._dns_host, self.port),
    ...<2 lines>...
        socket_options=self.socket_options,
    )
  File "C:\Users\524ta\AppData\Local\Programs\Python\Python313\Lib\site-packages\urllib3\util\connection.py", line 60, in create_connection
    for res in socket.getaddrinfo(host, port, family, socket.SOCK_STREAM):
               ~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\524ta\AppData\Local\Programs\Python\Python313\Lib\socket.py", line 977, in getaddrinfo
    for res in _socket.getaddrinfo(host, port, family, type, proto, flags):
               ~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
socket.gaierror: [Errno 11001] getaddrinfo failed

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "C:\Users\524ta\AppData\Local\Programs\Python\Python313\Lib\site-packages\urllib3\connectionpool.py", line 787, in urlopen
    response = self._make_request(
        conn,
    ...<10 lines>...
        **response_kw,
    )
  File "C:\Users\524ta\AppData\Local\Programs\Python\Python313\Lib\site-packages\urllib3\connectionpool.py", line 488, in _make_request
    raise new_e
  File "C:\Users\524ta\AppData\Local\Programs\Python\Python313\Lib\site-packages\urllib3\connectionpool.py", line 464, in _make_request
    self._validate_conn(conn)
    ~~~~~~~~~~~~~~~~~~~^^^^^^
  File "C:\Users\524ta\AppData\Local\Programs\Python\Python313\Lib\site-packages\urllib3\connectionpool.py", line 1093, in _validate_conn
    conn.connect()
    ~~~~~~~~~~~~^^
  File "C:\Users\524ta\AppData\Local\Programs\Python\Python313\Lib\site-packages\urllib3\connection.py", line 753, in connect
    self.sock = sock = self._new_conn()
                       ~~~~~~~~~~~~~~^^
  File "C:\Users\524ta\AppData\Local\Programs\Python\Python313\Lib\site-packages\urllib3\connection.py", line 205, in _new_conn
    raise NameResolutionError(self.host, self, e) from e
urllib3.exceptions.NameResolutionError: <urllib3.connection.HTTPSConnection object at 0x00000188441BB0E0>: Failed to resolve 'nrel.gov' ([Errno 11001] getaddrinfo failed)

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "C:\Users\524ta\AppData\Local\Programs\Python\Python313\Lib\site-packages\requests\adapters.py", line 486, in send
    resp = conn.urlopen(
        method=request.method,
    ...<9 lines>...
        chunked=chunked,
    )
  File "C:\Users\524ta\AppData\Local\Programs\Python\Python313\Lib\site-packages\urllib3\connectionpool.py", line 841, in urlopen
    retries = retries.increment(
        method, url, error=new_e, _pool=self, _stacktrace=sys.exc_info()[2]
    )
  File "C:\Users\524ta\AppData\Local\Programs\Python\Python313\Lib\site-packages\urllib3\util\retry.py", line 519, in increment
    raise MaxRetryError(_pool, url, reason) from reason  # type: ignore[arg-type]
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
urllib3.exceptions.MaxRetryError: HTTPSConnectionPool(host='nrel.gov', port=443): Max retries exceeded with url: /docs/fy24osti/87050.pdf (Caused by NameResolutionError("<urllib3.connection.HTTPSConnection object at 0x00000188441BB0E0>: Failed to resolve 'nrel.gov' ([Errno 11001] getaddrinfo failed)"))

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "C:\Users\524ta\OneDrive\Desktop\hackmatrix\research\omni_read.py", line 91, in <module>
    main()
    ~~~~^^
  File "C:\Users\524ta\OneDrive\Desktop\hackmatrix\research\omni_read.py", line 78, in main
    text = load_text(sys.argv[2])[:MAX_CHARS]
           ~~~~~~~~~^^^^^^^^^^^^^
  File "C:\Users\524ta\OneDrive\Desktop\hackmatrix\research\omni_read.py", line 55, in load_text
    r = requests.get(src, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
  File "C:\Users\524ta\AppData\Local\Programs\Python\Python313\Lib\site-packages\requests\api.py", line 73, in get
    return request("get", url, params=params, **kwargs)
  File "C:\Users\524ta\AppData\Local\Programs\Python\Python313\Lib\site-packages\requests\api.py", line 59, in request
    return session.request(method=method, url=url, **kwargs)
           ~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\524ta\AppData\Local\Programs\Python\Python313\Lib\site-packages\requests\sessions.py", line 589, in request
    resp = self.send(prep, **send_kwargs)
  File "C:\Users\524ta\AppData\Local\Programs\Python\Python313\Lib\site-packages\requests\sessions.py", line 703, in send
    r = adapter.send(request, **kwargs)
  File "C:\Users\524ta\AppData\Local\Programs\Python\Python313\Lib\site-packages\requests\adapters.py", line 519, in send
    raise ConnectionError(e, request=request)
requests.exceptions.ConnectionError: HTTPSConnectionPool(host='nrel.gov', port=443): Max retries exceeded with url: /docs/fy24osti/87050.pdf (Caused by NameResolutionError("<urllib3.connection.HTTPSConnection object at 0x00000188441BB0E0>: Failed to resolve 'nrel.gov' ([Errno 11001] getaddrinfo failed)"))
