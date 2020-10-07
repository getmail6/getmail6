# docs/COPYING 2a + DRY: https://github.com/getmail6/getmail6
# Please refer to the git history regarding who changed what and when in this file.

if git status | grep nothing; then
    make dist
    make up
    sed -i -e "s/name.*=.*getmail6./name = 'getmail'/g" setup.py
    make dist
    make up
    git reset --hard
else
    echo Commit changes first!
fi
