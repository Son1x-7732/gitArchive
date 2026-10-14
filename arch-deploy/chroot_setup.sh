#!/bin/bash
set -e

echo "=== Setting Timezone and Locale ==="
ln -sf /usr/share/zoneinfo/Asia/Kolkata /etc/localtime
hwclock --systohc
echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen
locale-gen
echo "LANG=en_US.UTF-8" > /etc/locale.conf
echo "arch-vm" > /etc/hostname

echo "=== Configuring Users ==="
echo "root:root" | chpasswd
useradd -m -G wheel -s /bin/zsh zen0
echo "zen0:password" | chpasswd
sed -i 's/^# %wheel ALL=(ALL:ALL) ALL/%wheel ALL=(ALL:ALL) ALL/' /etc/sudoers

echo "=== Adding CachyOS Repositories ==="
# Download and extract the official repository installer
curl -O https://mirror.cachyos.org/cachyos-repo.tar.xz
tar xvf cachyos-repo.tar.xz
cd cachyos-repo

# Run the integration script
./cachyos-repo.sh

# Clean up the installer files and go back to root directory
cd ..
rm -rf cachyos-repo cachyos-repo.tar.xz

echo "=== Installing Optimized CachyOS Packages ==="
pacman -S --noconfirm linux-cachyos linux-cachyos-headers cachyos-settings

echo "=== Configuring Limine Bootloader ==="
mkdir -p /boot/EFI/BOOT
cp /usr/share/limine/BOOTX64.EFI /boot/EFI/BOOT/

ROOT_UUID=$(blkid -s UUID -o value /dev/vda2)

# Write the Limine v7+ compliant configuration
cat << EOF > /boot/limine.conf
timeout: 5

/CachyOS (Optimized)
    protocol: linux
    path: boot():/vmlinuz-linux-cachyos
    module_path: boot():/initramfs-linux-cachyos.img
    cmdline: root=UUID=${ROOT_UUID} rw rootflags=subvol=@

/Arch Linux (Standard Kernel Fallback)
    protocol: linux
    path: boot():/vmlinuz-linux
    module_path: boot():/initramfs-linux.img
    cmdline: root=UUID=${ROOT_UUID} rw rootflags=subvol=@
EOF

echo "=== Configuring Snapper ==="
umount /.snapshots
rm -rf /.snapshots
snapper --no-dbus -c root create-config /
btrfs subvolume delete /.snapshots
mkdir /.snapshots
mount -a

echo "=== Enabling Display Manager ==="
systemctl enable NetworkManager.service
systemctl enable sddm.service

exit
