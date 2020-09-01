if git status | grep nothing; then
    make dist
    make up
    sed -i -e "s/name.*=.*getmail./name = 'getmail6'/g" setup.py
    make dist
    make up
    git reset --hard
else
    echo Commit changes first!
fi
