#!/bin/bash
set -e

# =========================================================================
# 🛑 PRE-FLIGHT SAFETY CHECKS 🛑
# =========================================================================
# 1. UEFI Boot Check
[[ -d /sys/firmware/efi/efivars ]] || {
    echo "🛑 FATAL: Live USB was not booted in UEFI mode. Aborting."
    exit 1
}

# 2. Permanent Hardware ID Targeting (Locks onto the Linux Micron SSD)
DISK="/dev/disk/by-id/nvme-Micron_3400_MTFDKBA512TFH_23013DE768E4"
PART_EFI="${DISK}-part1"
PART_ROOT="${DISK}-part2"

# Ultimate Fail-Safe Check: Block the script immediately if it targets the WD Blue Windows drive
[[ "$DISK" == *"WD_Blue"* ]] && { echo "🛑 FATAL: DISK is targeting the Windows drive!"; exit 1; }
[[ "$DISK" == *"SN5000"* ]] && { echo "🛑 FATAL: DISK is targeting the Windows drive!"; exit 1; }

echo "🚨 WARNING: This will completely WIPE your LINUX drive ($DISK) in 10 seconds."
echo "Your Windows drive (nvme1n1) is locked and WILL NOT be touched."
echo "Press Ctrl+C NOW to abort if you are unsure!"
sleep 10

echo "=== Clearing stale mounts on $DISK ==="
umount -A --recursive /mnt 2>/dev/null || true
for part in $(lsblk -ln -o NAME "$DISK" | tail -n +2); do
    umount "/dev/$part" 2>/dev/null || true
done
swapoff -a 2>/dev/null || true

echo "=== Wiping and Partitioning $DISK ==="
parted -s $DISK mklabel gpt \
  mkpart ESP fat32 1MiB 2048MiB set 1 esp on \
  mkpart root btrfs 2048MiB 100%

partprobe "$DISK"
udevadm settle

echo "=== Formatting Filesystems ==="
mkfs.vfat -F 32 $PART_EFI
mkfs.btrfs -f $PART_ROOT

echo "=== Creating CachyOS Btrfs Subvolumes ==="
mount $PART_ROOT /mnt
btrfs subvolume create /mnt/@
btrfs subvolume create /mnt/@home
btrfs subvolume create /mnt/@root
btrfs subvolume create /mnt/@srv
btrfs subvolume create /mnt/@cache
btrfs subvolume create /mnt/@tmp
btrfs subvolume create /mnt/@log
btrfs subvolume create /mnt/@snapshots
umount /mnt

echo "=== Mounting Subvolumes ==="
BTRFS_OPTS="noatime,compress=zstd:3"

mount -o subvol=@,$BTRFS_OPTS $PART_ROOT /mnt
mkdir -p /mnt/{home,root,srv,var/cache,var/tmp,var/log,boot,.snapshots}

mount -o subvol=@home,$BTRFS_OPTS $PART_ROOT /mnt/home
mount -o subvol=@root,$BTRFS_OPTS $PART_ROOT /mnt/root
mount -o subvol=@srv,$BTRFS_OPTS $PART_ROOT /mnt/srv
mount -o subvol=@cache,$BTRFS_OPTS $PART_ROOT /mnt/var/cache
mount -o subvol=@tmp,$BTRFS_OPTS $PART_ROOT /mnt/var/tmp
mount -o subvol=@log,$BTRFS_OPTS $PART_ROOT /mnt/var/log
mount -o subvol=@snapshots,$BTRFS_OPTS $PART_ROOT /mnt/.snapshots

chmod 1777 /mnt/var/tmp
mount -o umask=0077 $PART_EFI /mnt/boot

echo "=== Detecting Hardware Architecture ==="
UCODE_PKG="intel-ucode"
UCODE_IMG="/intel-ucode.img"

echo "=== Configuring CachyOS Repositories ==="
if grep -q "avx512f" /proc/cpuinfo; then
    echo "x86-64-v4 Architecture Detected."
    V4_PKG="cachyos-v4-mirrorlist"
    cat << 'REPO_EOF' > /mnt/cachy_repos.txt
[cachyos-v4]
Include = /etc/pacman.d/cachyos-v4-mirrorlist
[cachyos-core-v4]
Include = /etc/pacman.d/cachyos-v4-mirrorlist
[cachyos-extra-v4]
Include = /etc/pacman.d/cachyos-v4-mirrorlist
[cachyos]
Include = /etc/pacman.d/cachyos-mirrorlist
REPO_EOF
else
    echo "x86-64-v3 Architecture Detected (Acer Nitro 5 Default)."
    V4_PKG=""
    cat << 'REPO_EOF' > /mnt/cachy_repos.txt
[cachyos-v3]
Include = /etc/pacman.d/cachyos-v3-mirrorlist
[cachyos-core-v3]
Include = /etc/pacman.d/cachyos-v3-mirrorlist
[cachyos-extra-v3]
Include = /etc/pacman.d/cachyos-v3-mirrorlist
[cachyos]
Include = /etc/pacman.d/cachyos-mirrorlist
REPO_EOF
fi

echo "=== Enabling Multilib on Host Environment ==="
sed -i '/^#\[multilib\]/{s/^#//;n;s/^#//}' /etc/pacman.conf

# Inject a guaranteed Arch fallback mirror so the sync never fails
echo 'Server = https://mirrors.kernel.org/archlinux/$repo/os/$arch' >> /etc/pacman.d/mirrorlist

# Only sync the databases to prepare for pacstrap. Do NOT full-upgrade the live USB in RAM.
pacman -Sy

echo "=== Pacstrap: Installing Hardware-Tuned Base ==="
pacstrap -K /mnt base linux-cachyos linux-cachyos-headers linux-firmware $UCODE_PKG btrfs-progs mkinitcpio mesa vulkan-intel intel-media-driver nvidia nvidia-utils lib32-nvidia-utils sddm plasma-desktop konsole dolphin networkmanager dnsmasq iptables-nft plasma-nm pipewire pipewire-pulse pipewire-alsa wireplumber plasma-pa switcheroo-control firewalld sudo micro zsh zram-generator cachyos-keyring cachyos-mirrorlist cachyos-v3-mirrorlist ananicy-cpp limine efibootmgr bluez bluez-utils bluedevil sof-firmware alsa-firmware alsa-utils zsh-syntax-highlighting zsh-autosuggestions zsh-history-substring-search fzf eza bat pkgfile kscreen spectacle tesseract tesseract-data-eng ark p7zip unrar unzip $V4_PKG

echo "=== Injecting Explicit CachyOS Repositories ==="
awk '/^\[core\]/{exit} {print}' /mnt/etc/pacman.conf > /mnt/etc/pacman.conf.new
cat /mnt/cachy_repos.txt >> /mnt/etc/pacman.conf.new
awk '/^\[core\]/{p=1} p {print}' /mnt/etc/pacman.conf >> /mnt/etc/pacman.conf.new
mv /mnt/etc/pacman.conf.new /mnt/etc/pacman.conf
rm /mnt/cachy_repos.txt

echo "=== Enabling Multilib on Target System ==="
sed -i '/^#\[multilib\]/{s/^#//;n;s/^#//}' /mnt/etc/pacman.conf

echo "=== Bootstrapping GPG Keyrings ==="
arch-chroot /mnt pacman-key --init
arch-chroot /mnt pacman-key --populate archlinux cachyos
arch-chroot /mnt pacman-key --recv-keys F3B607488DB35A47
arch-chroot /mnt pacman-key --lsign-key F3B607488DB35A47

echo "=== Tuning zram-generator ==="
mkdir -p /mnt/etc/systemd
cat << 'ZRAM_EOF' > /mnt/etc/systemd/zram-generator.conf
[zram0]
zram-size = ram / 2
compression-algorithm = zstd
swap-priority = 100
fs-type = swap
ZRAM_EOF

echo "=== Generating Fstab ==="
genfstab -U /mnt > /mnt/etc/fstab
sed -i 's/,subvolid=[0-9]*//' /mnt/etc/fstab

echo "=== Extracting Hardware UUID ==="
ROOT_UUID=$(blkid -s UUID -o value $PART_ROOT)
[ -z "$ROOT_UUID" ] && { echo "🛑 FATAL: Could not read UUID from $PART_ROOT"; exit 1; }

# Bridge host variables into the chroot via an environment state file
echo "DISK=\"$DISK\"" > /mnt/chroot_env.sh
echo "ROOT_UUID=\"$ROOT_UUID\"" >> /mnt/chroot_env.sh
echo "UCODE_IMG=\"$UCODE_IMG\"" >> /mnt/chroot_env.sh

echo "=== Generating Chroot Payload ==="
cat << 'EOF' > /mnt/chroot_setup.sh
#!/bin/bash
set -e

# Load variables passed from the host script
source /chroot_env.sh
rm /chroot_env.sh

echo "=== Setting Timezone & Locale ==="
ln -sf /usr/share/zoneinfo/Asia/Kolkata /etc/localtime
hwclock --systohc
sed -i 's/#en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen
locale-gen
echo "LANG=en_US.UTF-8" > /etc/locale.conf
echo "void" > /etc/hostname

echo "=== Creating User ==="
useradd -m -G wheel -s /bin/zsh nix

echo "=== Setting Passwords ==="
set +e
echo "Enter password for ROOT:"
while ! passwd; do echo "Failed. Try again."; done
echo "Enter password for nix:"
while ! passwd nix; do echo "Failed. Try again."; done
set -e

echo "=== Configuring Sudo ==="
sed -i 's/# %wheel ALL=(ALL:ALL) ALL/%wheel ALL=(ALL:ALL) ALL/' /etc/sudoers

echo "=== Enabling System Services ==="
systemctl enable NetworkManager
systemctl enable sddm
systemctl enable firewalld
systemctl enable switcheroo-control
systemctl enable bluetooth.service

echo "=== Forcing SDDM to Native Wayland (KDE Guidelines) ==="
mkdir -p /etc/sddm.conf.d
cat << SDDM_EOF > /etc/sddm.conf.d/10-wayland.conf
[General]
DisplayServer=wayland
GreeterEnvironment=QT_WAYLAND_SHELL_INTEGRATION=layer-shell

[Wayland]
CompositorCommand=kwin_wayland --drm --no-lockscreen --no-global-shortcuts --locale1
SDDM_EOF

echo "=== Fixing mkinitcpio for Btrfs ==="
sed -i 's/^MODULES=.*/MODULES=(btrfs)/' /etc/mkinitcpio.conf
mkinitcpio -P

echo "=== Installing Limine Bootloader ==="
mkdir -p /boot/EFI/BOOT
cp /usr/share/limine/BOOTX64.EFI /boot/EFI/BOOT/

# Dynamically construct the configuration block based on microcode presence
if [ -n "$UCODE_IMG" ]; then
    MODULE_LINE="    module_path: boot():$UCODE_IMG"
else
    MODULE_LINE=""
fi

cat << LIMINECONF > /boot/limine.conf
timeout: 3
remember_last_entry: yes

/CachyOS (Bare Metal)
    protocol: linux
    kernel_path: boot():/vmlinuz-linux-cachyos
$MODULE_LINE
    module_path: boot():/initramfs-linux-cachyos.img
    cmdline: root=UUID=$ROOT_UUID rootflags=subvol=@ rw quiet nvidia.NVreg_UseKernelSuspendNotifiers=1 nvidia_drm.fbdev=1 acpi_backlight=native nowatchdog

/CachyOS (Fallback)
    protocol: linux
    kernel_path: boot():/vmlinuz-linux-cachyos
$MODULE_LINE
    module_path: boot():/initramfs-linux-cachyos-fallback.img
    cmdline: root=UUID=$ROOT_UUID rootflags=subvol=@ rw quiet nvidia.NVreg_UseKernelSuspendNotifiers=1 nvidia_drm.fbdev=1 acpi_backlight=native nowatchdog
LIMINECONF

# Secure registration inside UEFI NVRAM table
efibootmgr --create --disk "$DISK" --part 1 --loader /EFI/BOOT/BOOTX64.EFI --label "CachyOS (Limine)" --unicode
EOF

echo "=== Executing Chroot Payload ==="
chmod +x /mnt/chroot_setup.sh
arch-chroot -S /mnt /chroot_setup.sh

echo "=== CLEANING UP ==="
rm -f /mnt/chroot_setup.sh

echo "=== INSTALLATION COMPLETE! ==="
echo "You are completely ready. Run: umount -R /mnt && reboot"
