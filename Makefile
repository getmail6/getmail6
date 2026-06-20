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

.PHONY: dockertest
dockertest:
	(cd test && source ./prepare.sh && restart_dms && d_docker "bats getmaildms.bats") || true

.PHONY: fortest
fortest:
	pip install -e .
	pip install pytest

.PHONY: unittests
unittests: fortest
	pytest test/test.py test/test_mock_servers.py

.PHONY: test
test: unittests dockertest
	(cd test && docker compose down) || true

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

.PHONY: docrepo
docrepo: # update https://github.com/getmail6/getmail6.github.io
	yes | cp docs/*.html ../getmail6.github.io
	yes | cp docs/getmailrc-examples ../getmail6.github.io
	(cd ../getmail6.github.io && git add . && git commit -m "doc")
	(cd ../getmail6.github.io && V=$(../getmail6/getmail --version | cut -d ' ' -f 2) git commit --amend -m "v$V")
	(cd ../getmail6.github.io && git push)

# ./pypi.sh to upload to PYPI no more needed due to
# .github/workflows/publish.yml
# .github/workflows/publish6.yml
.PHONY: up6
up6: dist
	twine upload dist/`ls dist -rt *.whl | tail -1` dist/`ls dist -rt *.tar.gz | tail -1` -u__token__ -p`pass show pypi.org/getmail6_api_token`

.PHONY: up
up: dist
	twine upload dist/`ls dist -rt *.whl | tail -1` dist/`ls dist -rt *.tar.gz | tail -1` -u__token__ -p`pass show pypi.org/getmail_api_token`

# "make doc" and commit all changes then run "make tag". Then, to make the release go to
# https://github.com/getmail6/getmail6
.PHONY: tag
tag: dist docrepo
	$(eval TAGMSG="v$(shell ./getmail --version | cut -d ' ' -f 2)")
	echo $(TAGMSG)
	git commit -am "$(TAGMSG)"
	git push
	git tag -s $(TAGMSG) -m"$(TAGMSG)"
	git verify-tag $(TAGMSG)
	git push origin $(TAGMSG) --follow-tags

.PHONY: cleandocker
cleandocker:
	docker network prune
	docker rm -vf $$(docker ps -aq)
	docker rmi -f $$(docker images -aq)

.PHONY: log
log:
	cd test && docker compose logs

