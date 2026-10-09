Traceback (most recent call last):
  File "C:\Users\524ta\OneDrive\Desktop\hackmatrix\research\omni_read.py", line 91, in <module>
    main()
    ~~~~^^
  File "C:\Users\524ta\OneDrive\Desktop\hackmatrix\research\omni_read.py", line 78, in main
    text = load_text(sys.argv[2])[:MAX_CHARS]
           ~~~~~~~~~^^^^^^^^^^^^^
  File "C:\Users\524ta\OneDrive\Desktop\hackmatrix\research\omni_read.py", line 56, in load_text
    r.raise_for_status()
    ~~~~~~~~~~~~~~~~~~^^
  File "C:\Users\524ta\AppData\Local\Programs\Python\Python313\Lib\site-packages\requests\models.py", line 1021, in raise_for_status
    raise HTTPError(http_error_msg, response=self)
requests.exceptions.HTTPError: 403 Client Error: Forbidden for url: https://www.mdpi.com/2073-4433/16/8/957/pdf
