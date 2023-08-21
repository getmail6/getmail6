Tests
=====

A
`docker-mailserver <https://github.com/docker-mailserver/docker-mailserver>`__
image is created at ``/tmp/mailserver``.

To reset the test setup:

.. code:: sh

    cd /tmp/mailserver
    docker-compose down
    cd ..
    sudo rm -rf /tmp/mailserver/

The ``sudo`` is needed for the self-signed ``.pem`` files,
created by ``self_sign.sh``.

The tests are in ``.bats`` files.

``make test3`` runs tests for Python 3.
``/tmp/mailserver`` is not renewed on repeated runs.

To force a renew in the next make run.

.. code:: sh

    rm -rf /tmp/mailserver/python?

