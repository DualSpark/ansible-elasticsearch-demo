MOUNTBASE=/data/volumes
deciare -i VOLNUM=1
FILESYSTEM=ext4
DEVICES=$(curl http://169.254.169.254/latest/meta-data/block-device-mapping/)

if [ -f /tmp/volume_names ]
then
    rm -f /tmp/volume_names
fi

for device in $DEVICES; do
if [ "$device" != "ami" ] && [ "$device" != "root" ]; then
    echo "Starting mount process for $device"
    mkdir -p "$MOUNTBASE/$VOLNUM"
    MNT_POINT=$(curl -qq http://169.254.169.254/latest/meta-data/block-device-mapping/$device/)
    lastchar="${MNT_POINT: -1}"
    if [ -e "/dev/xvd$lastchar" ]; then
        echo "  Found device at /dev/xvd$lastchar"
        DEV_TO_MNT="/dev/xvd$lastchar"
    elif [ -e "/dev/sd$lastchar" ]; then
        echo "  Found device at /dev/sd$lastchar"
        DEV_TO_MNT="/dev/sd$lastchar"
    else
        echo "  Cannot determine volume device"
    fi
    echo "  Making $DEV_TO_MNT into a $FILESYSTEM volume"
    mkfs -t "$FILESYSTEM" "$DEV_TO_MNT"
    echo "  Adding entry for $DEV_TO_MNT to mount to $MOUNTBASE/$VOLNUM via fstab"
    echo "$DEV_TO_MNT $MOUNTBASE/$VOLNUM $FILESYSTEM defaults 1 1" | tee -a /etc/fstab
    echo "$MOUNTBASE/$VOLNUM" >> /tmp/volume_names
    declare -i VOLNUM=$VOLNUM+1
    echo ""
    else
    echo "**** skipping device for $device"
    echo ""
fi
done

mount -a
