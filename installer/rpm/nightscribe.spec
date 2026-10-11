############################################################
# NightScribe - RPM spec (Fedora / openSUSE)
#
# Built by the "Linux packages" GitHub Actions workflow on a Fedora runner:
#   rpmbuild -bb --define "_version <v>" installer/rpm/nightscribe.spec
# Output: nightscribe-<v>-1.noarch.rpm
#
# The package uses the SYSTEM Python and lets RPM's automatic Python
# dependency generator read the imports, so the Requires are the distro's own
# python3dist(...) packages (PySide6, astropy, scipy, numpy, matplotlib,
# photutils, lxml, requests, PyYAML, platformdirs, Pillow). imageio-ffmpeg is
# a WEAK dependency (Recommends): it only powers the MP4 export, and Fedora
# does not package it, so the GIF and the montage must keep working without
# it (ADR-079).
#
# Find_Orb is shipped inside the package. It is GPLv2 with an extra
# commercial-use clause from Project Pluto: fine for this non-commercial
# GPLv3 app (see ADR-079).
############################################################

%if 0%{?_version}
%define version %{_version}
%else
%define version 0.0.0
%endif

Name:           nightscribe
Version:        %{version}
Release:        1%{?dist}
Summary:        Plan, reduce and report an astronomy night
License:        GPL-3.0-or-later
URL:            https://github.com/irydeo/nightscribe
# The source tarball is assembled by the CI (this spec is built from the
# checked-out tree); %{SOURCE0} points at it.
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  python3-devel

%description
NightScribe plans the night's best targets, captures and reduces the images
(calibration, track & stack astrometry, photometry) and drafts the report and
the social post.

%package -n %{name}
Recommends:     python3dist(imageio-ffmpeg)
%description -n %{name}
NightScribe plans the night's best targets, captures and reduces the images
(calibration, track & stack astrometry, photometry) and drafts the report and
the social post.

%prep
%setup -q

%build
# Nothing to compile: it is pure Python.

%install
rm -rf %{buildroot}
install -d %{buildroot}%{python3_sitelib}
cp -a nightscribe %{buildroot}%{python3_sitelib}/nightscribe
find %{buildroot}%{python3_sitelib} -name '__pycache__' -type d \
    -exec rm -rf {} +
install -d %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/nightscribe <<'EOF'
#!/bin/sh
exec python3 -m nightscribe "$@"
EOF
chmod 0755 %{buildroot}%{_bindir}/nightscribe
install -d %{buildroot}%{_datadir}/applications
install -m 0644 installer/nightscribe.desktop \
    %{buildroot}%{_datadir}/applications/nightscribe.desktop
for s in 16 32 48 64 128 256; do
    install -d %{buildroot}%{_datadir}/icons/hicolor/${s}x${s}/apps
    install -m 0644 nightscribe/assets/appicon-${s}.png \
        %{buildroot}%{_datadir}/icons/hicolor/${s}x${s}/apps/nightscribe.png
done
# Find_Orb, when the CI dropped a prepared tree in ./findorb-payload
if [ -d findorb-payload ]; then
    install -d %{buildroot}%{_prefix}/lib/nightscribe
    cp -a findorb-payload %{buildroot}%{_prefix}/lib/nightscribe/findorb
fi

%files
%{python3_sitelib}/nightscribe
%{_bindir}/nightscribe
%{_datadir}/applications/nightscribe.desktop
%{_datadir}/icons/hicolor/*/apps/nightscribe.png
%{_prefix}/lib/nightscribe/findorb

%changelog
* Sun Oct 11 2026 Francisco Jose Calvo Fernandez <irydeo@users.noreply.github.com> - %{version}-1
- First packaged build.
