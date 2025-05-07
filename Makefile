# docs/COPYING 2a + DRY: https://github.com/getmail6/getmail6
# Please refer to the git history regarding who changed what and when in this file.

# Needs Docker Daemon running
# systemctl start docker

.PHONY: doc
doc:
	links -dump docs/documentation.html > docs/documentation.txt
	links -dump docs/configuration.html > docs/configuration.txt
	links -dump docs/faq.html > docs/faq.txt
	links -dump docs/troubleshooting.html > docs/troubleshooting.txt

.PHONY: testclean
testclean:
	[ -d /tmp/mailserver/ ] && (cd /tmp/mailserver && docker-compose down) || true
	[ -d /tmp/mailserver/ ] && sudo rm -rf /tmp/mailserver || true

.PHONY: test3
test3:
	cd test && ./prepare_test.sh
	cd /tmp/mailserver && test/bats/bin/bats test/test_getmail_with_docker_mailserver.bats

.PHONY: fortest
fortest:
	pip install pytest

.PHONY: unittests
unittests: fortest
	pytest test/test.py test/test_mock_servers.py

.PHONY: test
test: unittests testclean test3
	cd /tmp/mailserver && docker-compose down

.PHONY: lint
lint:
	ruff check .

.PHONY: check
check: lint
	/usr/bin/man -l docs/getmail.1
	/usr/bin/man -l docs/getmails.1
	/usr/bin/man -l docs/getmail_fetch.1
	/usr/bin/man -l docs/getmail_maildir.1
	/usr/bin/man -l docs/getmail_mbox.1
	restview --long-description --strict

.PHONY: dist
dist: doc
	echo "need sudo to create wheel"
	sudo python setup.py bdist_wheel sdist
	echo "note:"
	echo "use ./pypi.sh to upload to PYPI"

# use ./pypi.sh to upload to PYPI
.PHONY: up6
up6: dist
	twine upload dist/`ls dist -rt *.whl | tail -1` dist/`ls dist -rt *.tar.gz | tail -1` -u__token__ -p`pass show pypi.org/getmail6_api_token`

.PHONY: up
up: dist
	twine upload dist/`ls dist -rt *.whl | tail -1` dist/`ls dist -rt *.tar.gz | tail -1` -u__token__ -p`pass show pypi.org/getmail_api_token`

.PHONY: tag
tag: dist
	$(eval TAGMSG="v$(shell ./getmail --version | cut -d ' ' -f 2)")
	echo $(TAGMSG)
	git tag -s $(TAGMSG) -m"$(TAGMSG)"
	git verify-tag $(TAGMSG)
	git push origin $(TAGMSG) --follow-tags

.PHONY: cleandocker
cleandocker:
	docker network prune
	docker rm -vf $$(docker ps -aq)
	docker rmi -f $$(docker images -aq)
