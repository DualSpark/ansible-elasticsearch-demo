#!/bin/bash
AWS_SQS_QUEUE=
AWS_SQS_REGION=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
apt-get update -y
apt-get upgrade -y
apt-get install python-pip sysstat -y
pip install beaver==31
mkdir -p /etc/beaver

INSTANCE_INFO=$(curl http://169.254.169.254/latest/dynamic/instance-identity/document/)
AWS_REGION=$(echo $INSTANCE_INFO | jq --raw-output '.region')
AWS_AZ=$(echo $INSTANCE_INFO | jq --raw-output '.availabilityZone')
AWS_INSTANCE_ID=$(echo $INSTANCE_INFO | jq --raw-output '.instanceId')
AWS_INSTANCE_TYPE=$(echo $INSTANCE_INFO | jq --raw-output '.instanceType')
AWS_AMI_ID=$(echo $INSTANCE_INFO | jq --raw-output '.imageId')
AWS_ACCOUNT_ID=$(echo $INSTANCE_INFO | jq --raw-output '.accountId')

$ADD_FIELD="aws_region, $AWS_REGION, aws_az, $AWS_AZ, aws_instance_id, $AWS_INSTANCE_ID, aws_instance_type, $AWS_INSTANCE_TYPE, aws_ami_id, $AWS_AMI_ID, aws_account_id, $AWS_ACCOUNT_ID"
mkdir -p /etc/beaver
cat > /etc/beaver/beaver.conf << EOF 
[beaver]
sqs_aws_region: $AWS_SQS_REGION 
sqs_aws_queue: $AWS_SQS_QUEUE
sqs_aws_access_key: $AWS_ACCESS_KEY_ID
sqs_aws_secret_key: $AWS_SECRET_ACCESS_KEY 
logstash_version: 1

[/var/log/*log]
type: syslog
exclude: (messages|secure)
add_field: $ADD_FIELD

#add more here to pull more logs in... documentation is located at https://github.com/josegonzalez/beaver/blob/master/docs/user/usage.rst

EOF

chmod +r /etc/beaver/beaver.conf

cat > /etc/init.d/beaver << EOF
#!/bin/bash -
### BEGIN INIT INFO
# Provides:          beaver
# Required-Start:    \$local_fs \$remote_fs \$network
# Required-Stop:     \$local_fs \$remote_fs \$network
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: Start up the Beaver at boot time
# Description:       Enable Log Sender provided by beaver.
### END INIT INFO

BEAVER_NAME='beaver'
BEAVER_CMD='beaver -c /etc/beaver/beaver.conf -t sqs'
RUNDIR='/var/run/beaver'
BEAVER_PID=\${RUNDIR}/logstash_beaver.pid
BEAVER_USER='root'
LOGDIR='/var/log/beaver'
BEAVER_LOG=\${LOGDIR}/logstash_beaver.log
PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
export PATH
IFS=\$' \t\n'
export IFS
BEAVER_BIN="\$(which "\${BEAVER_NAME}")"
[ -r /etc/init.d/functions ] && . /etc/init.d/functions
[ -r /lib/lsb/init-functions ] && . /lib/lsb/init-functions
[ -r "/etc/default/\${BEAVER_NAME}" ] && . "/etc/default/\${BEAVER_NAME}"
do_start() {
    test -f "\${BEAVER_BIN}" || exit 0
    if is_up
    then
        echo \$'Log Sender server daemon already started.'
        return 0
    fi
    mkdir -p \$RUNDIR
    chown \$BEAVER_USER \$RUNDIR
    mkdir -p \$LOGDIR
    chown \$BEAVER_USER \$LOGDIR
    echo -n \$"Log Sender server daemon: \${BEAVER_NAME}"
    su - "\${BEAVER_USER}" -s '/bin/bash' -c "\${BEAVER_CMD} >> \${BEAVER_LOG} 2>&1 & echo \$! > \${BEAVER_PID}"
    echo '.'
}
do_stop() {
    test -f "\${BEAVER_BIN}" || exit 0
    if ! is_up
    then
        echo \$'Log Sender server daemon already stopped.'
        return 0
    fi
    echo -n \$"Stopping Log Sender server daemon: \${BEAVER_NAME}"
    do_kill
    while is_up
    do
        echo -n '.'
        sleep 1
    done
    echo '.'
}
beaver_pid() {
    tail -1 "\${BEAVER_PID}" 2> /dev/null
}
is_up() {
    PID="\$(beaver_pid)"
    [ x"\${PID}" != x ] && ps -p "\${PID}" -o comm h 2> /dev/null | grep -qFw "\${BEAVER_NAME}"
}
do_kill() {
    PID="\$(beaver_pid)"
    [ x"\${PID}" != x ] && su - "\${BEAVER_USER}" -c "kill -TERM \${PID}"
}
do_restart() {
    test -f "\${BEAVER_BIN}" || exit 0
    do_stop
    sleep 1
    do_start
}
do_status() {
    test -f "\${BEAVER_BIN}" || exit 0
    if is_up
    then
        echo "\${BEAVER_NAME} is running."
        exit 0
    else
        echo "\${BEAVER_NAME} is not running."
        exit 1
    fi
}
do_usage() {
    echo \$"Usage: \$0 {start | stop | restart | force-reload | status}"
    exit 1
}
case "\$1" in
start)
    do_start
    exit "\$?"
    ;;
stop)
    do_stop
    exit "\$?"
    ;;
restart|force-reload)
    do_restart
    exit "\$?"
    ;;
status)
    do_status
    ;;
*)
    do_usage
    ;;
esac
EOF

chmod +x /etc/init.d/beaver
chown root:root /etc/init.d/beaver
mkdir -p /var/log/beaver
mkdir -p /var/lib/beaver

/usr/sbin/update-rc.d -f beaver defaults
service beaver start
