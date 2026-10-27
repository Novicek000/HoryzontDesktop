%{!?_unitdir:%global _unitdir /usr/lib/systemd/system}
Name:           horyzont
Version:        0.4.3
Release:        1%{?dist}
Summary:        Classic desktop environment for Fedora (labwc + Qt)
License:        GPL-3.0-or-later
URL:            https://github.com/Novicek000/HoryzontDesktop
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  systemd-rpm-macros
Requires:       labwc >= 0.8.2
Requires:       python3-pyside6
Requires:       qt6-qtwayland
Requires:       python3-psutil
Requires:       python3-pefile
Requires:       wlr-randr
Requires:       xdg-user-dirs
Requires:       polkit
Recommends:     wine-tahoma-fonts
Recommends:     fedora-logos
Recommends:     grim
Recommends:     swayidle
Recommends:     swaylock
Recommends:     NetworkManager
Recommends:     bluez
Recommends:     pulseaudio-utils
Recommends:     7zip
Recommends:     unar
Recommends:     flatpak
Recommends:     PackageKit
Recommends:     lxpolkit
Recommends:     qt6-qtmultimedia
Recommends:     pipewire-utils
Recommends:     gstreamer1-plugins-good
Recommends:     dejavu-sans-fonts
Recommends:     bluez-obexd
Recommends:     pciutils
Recommends:     usbutils
Recommends:     hwdata
Recommends:     xdg-desktop-portal-gtk
Recommends:     xdg-desktop-portal-wlr
Recommends:     gnome-keyring

%description
Horyzont is a classic, early-2000s style desktop environment: taskbar with
Start menu, desktop icons, Explorer with a task pane, Notepad, Command Prompt,
Control Panel, Task Manager and Horyzont Updates. It runs on the labwc Wayland
compositor and can render user-supplied .msstyles visual styles and .msicon
icon packs.

%prep
%autosetup

%build

%install
mkdir -p %{buildroot}%{_datadir}/horyzont %{buildroot}%{_bindir} %{buildroot}%{_libexecdir}/horyzont \
         %{buildroot}%{_datadir}/applications %{buildroot}%{_datadir}/wayland-sessions \
         %{buildroot}%{_unitdir} %{buildroot}%{_datadir}/polkit-1/actions
cp -r horyzont docs tools %{buildroot}%{_datadir}/horyzont/
find %{buildroot}%{_datadir}/horyzont -name __pycache__ -prune -exec rm -rf {} +
for f in bin/*; do
  sed 's#@PKGDIR@#%{_datadir}/horyzont#g' "$f" > %{buildroot}%{_bindir}/$(basename "$f")
  chmod 755 %{buildroot}%{_bindir}/$(basename "$f")
done
ln -s %{_datadir}/horyzont/tools/make-msicon.sh %{buildroot}%{_bindir}/horyzont-msicon
cat > %{buildroot}%{_libexecdir}/horyzont/update-agent <<AGENT
#!/bin/sh
export PYTHONPATH=%{_datadir}/horyzont
exec /usr/bin/python3 -m horyzont update-agent "\$@"
AGENT
chmod 755 %{buildroot}%{_libexecdir}/horyzont/update-agent
sed 's#@AGENT@#%{_libexecdir}/horyzont/update-agent#g' share/systemd/horyzont-updates.service > %{buildroot}%{_unitdir}/horyzont-updates.service
install -m 644 share/systemd/horyzont-updates.timer %{buildroot}%{_unitdir}/
sed 's#@AGENT@#%{_libexecdir}/horyzont/update-agent#g' share/polkit/org.horyzont.update-agent.policy > %{buildroot}%{_datadir}/polkit-1/actions/org.horyzont.update-agent.policy
install -m 644 share/applications/*.desktop share/applications/horyzont-mimeapps.list %{buildroot}%{_datadir}/applications/
install -D -m 644 share/xdg-desktop-portal/horyzont-portals.conf %{buildroot}%{_datadir}/xdg-desktop-portal/horyzont-portals.conf
install -m 644 share/wayland-sessions/horyzont.desktop %{buildroot}%{_datadir}/wayland-sessions/
%{?py_byte_compile:%py_byte_compile %{python3} %{buildroot}%{_datadir}/horyzont/horyzont}

%post
%{?systemd_post:%systemd_post horyzont-updates.timer}

%preun
%{?systemd_preun:%systemd_preun horyzont-updates.timer}

%postun
%{?systemd_postun:%systemd_postun horyzont-updates.timer}

%files
%license LICENSE
%doc README.md
%{_bindir}/horyzont
%{_bindir}/horyzont-*
%{_libexecdir}/horyzont/
%{_datadir}/horyzont/
%{_datadir}/applications/horyzont-*.desktop
%{_datadir}/applications/horyzont-mimeapps.list
%{_datadir}/xdg-desktop-portal/horyzont-portals.conf
%{_datadir}/wayland-sessions/horyzont.desktop
%{_unitdir}/horyzont-updates.service
%{_unitdir}/horyzont-updates.timer
%{_datadir}/polkit-1/actions/org.horyzont.update-agent.policy

%changelog
* Wed Oct 28 2026 Horyzont <horyzont@example.org> - 0.4.3-1
- Smooth indeterminate progress bars (steady 60 fps timer), full-width progress bars
- Minimize/maximize buttons for GTK client-side decorated apps (Firefox, GNOME apps)

* Wed Oct 28 2026 Horyzont <horyzont@example.org> - 0.4.2-1
- Fix: password dialog could not take keyboard focus (XWayland modal-dialog focus redirect)
- Require qt6-qtwayland, warn when Qt runs through XWayland; clear error text after failed authentication
- Fix Print Screen keybinding XML for labwc 0.9
* Wed Oct 28 2026 Horyzont <horyzont@example.org> - 0.4.1-1
- Taskbar auto-hide, smoother Explorer resizing, ascending sort by default, blue light-ribbons wallpaper
- Fixes: Display Settings without refresh-rate list, WordPad asking to save an empty document,
  "Remove from This List" for frequently used programs
* Tue Oct 27 2026 Horyzont <horyzont@example.org> - 0.4.0-1
- Display resolution, refresh rate and scaling (persistent); taskbar hides for fullscreen windows
- Volume Control, Device Manager, power profiles and lid action, tray icon hiding and customization
- Start menu context menu with Send To; Bluetooth Send To; new wallpapers
- FileManager1 service, Horyzont-only default applications, XDG portal config, gnome-keyring
- Program icons for .exe files, Wine/Bottles suggestion, classic Open With dialog
* Tue Oct 27 2026 Horyzont <horyzont@example.org> - 0.3.0-1
- New programs: Calculator, Character Map, Paint, WordPad (RTF/DOCX/ODT), Minesweeper, Solitaire,
  Picture and Fax Viewer, Media Player, Sound Recorder; installer checks every dependency
* Tue Oct 27 2026 Horyzont <horyzont@example.org> - 0.2.1-1
- Program icons in the notification area (StatusNotifierItem/AppIndicator, dbusmenu),
  notifications shown as balloons (org.freedesktop.Notifications), XDG autostart
* Tue Oct 27 2026 Horyzont <horyzont@example.org> - 0.2.0-1
- Command Prompt, archives (ZIP/RAR/7z with passwords), Wi-Fi and Bluetooth, Horyzont Updates,
  own authentication dialogs, pointer and sound schemes, .msicon icon packs, many fixes
* Mon Oct 26 2026 Horyzont <horyzont@example.org> - 0.1.0-1
- First release: shell, Explorer, Notepad, Control Panel, Task Manager, .msstyles support
