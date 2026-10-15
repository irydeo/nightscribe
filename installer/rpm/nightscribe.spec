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
# it (ADR-079). pyopencl is a hard dependency (ADR-091): the portable GPU
# backend travels with the app.
#
# Find_Orb is shipped inside the package. It is GPLv2 with an extra
# commercial-use clause from Project Pluto: fine for this non-commercial
# GPLv3 app (see ADR-079).
############################################################

# The version is passed by the CI as _version; a bare build falls back to
# 0.0.0. (The usual numeric conditional idiom does not accept a string
# version: it is a parse error, "bad condition".)
%define version %{?_version}%{!?_version:0.0.0}

# The package ships a PREBUILT binary (`fo`, from conda-forge) that carries no
# build-id note, and Fedora's find-debuginfo --strict-build-id refuses to
# process it ("No build ID note found"), failing the whole build. There is
# nothing of ours to debug in a vendored binary, so the debuginfo package is
# disabled.
%global debug_package %{nil}

Name:           nightscribe
Version:        %{version}
Release:        1%{?dist}
Summary:        Plan, reduce and report an astronomy night
License:        GPL-3.0-or-later
URL:            https://github.com/irydeo/nightscribe
# The source tarball is assembled by the CI (this spec is built from the
# checked-out tree); %{SOURCE0} points at it.
Source0:        %{name}-%{version}.tar.gz
BuildRequires:  python3-devel
# imageio-ffmpeg is OPTIONAL: it only powers the MP4 animation export, and
# Fedora does not package it. Without it the GIF and the montage keep working.
Recommends:     python3dist(imageio-ffmpeg)
# pyopencl IS required (ADR-091): it is the portable GPU backend and the app
# ships it. It is named BY HAND because the import is lazy (inside the probe),
# so RPM's automatic Python dependency generator never sees it. It pulls the
# ICD loader (ocl-icd) with it. The acceleration stays off by default and the
# CPU path runs unchanged with no OpenCL device.
Requires:       python3dist(pyopencl)

%description
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
# The version, in the two shapes the app understands: the standard dist-info
# (importlib.metadata.version) and a plain file the version module reads as a
# last resort. Without the dist-info the installed app reports "0.0.0" and the
# update detection never fires (ADR-087 rev).
# %{version} lands in the METADATA verbatim, and RPM's pythondistdeps parses
# that field with `packaging`, which is strict PEP 440: a local segment must
# keep its '+'. Passing a mangled version here (e.g. '0.1.0.dev3-g1a2b3c4')
# makes the generator raise "Invalid version" and fails the build after the
# package is assembled (hit on 2026-10-15).
install -d %{buildroot}%{python3_sitelib}/nightscribe-%{version}.dist-info
printf 'Metadata-Version: 2.1\nName: nightscribe\nVersion: %{version}\n' \
    > %{buildroot}%{python3_sitelib}/nightscribe-%{version}.dist-info/METADATA
install -d %{buildroot}%{_datadir}/nightscribe
printf '%s\n' '%{version}' > %{buildroot}%{_datadir}/nightscribe/version
# The documentation, where paths.docs_dir() looks on a system install:
# without it Help > Documentation and the offline assistant index are empty.
install -d %{buildroot}%{_datadir}/nightscribe/docs
cp -a docs/. %{buildroot}%{_datadir}/nightscribe/docs/
install -d %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/nightscribe <<'EOF'
#!/bin/sh
exec python3 -m nightscribe "$@"
EOF
chmod 0755 %{buildroot}%{_bindir}/nightscribe
install -d %{buildroot}%{_datadir}/applications
install -m 0644 installer/io.github.irydeo.nightscribe.desktop \
    %{buildroot}%{_datadir}/applications/io.github.irydeo.nightscribe.desktop
# The AppStream metainfo: licence, developer and icon for the software centre
# (its id must match the .desktop file's name).
install -d %{buildroot}%{_datadir}/metainfo
install -m 0644 installer/io.github.irydeo.nightscribe.metainfo.xml \
    %{buildroot}%{_datadir}/metainfo/io.github.irydeo.nightscribe.metainfo.xml
# The licence, where RPM's %license macro expects it.
install -d %{buildroot}%{_datadir}/licenses/%{name}
install -m 0644 LICENSE %{buildroot}%{_datadir}/licenses/%{name}/LICENSE
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
%{python3_sitelib}/nightscribe-%{version}.dist-info
%{_bindir}/nightscribe
%{_datadir}/applications/io.github.irydeo.nightscribe.desktop
%{_datadir}/metainfo/io.github.irydeo.nightscribe.metainfo.xml
%license %{_datadir}/licenses/%{name}/LICENSE
%{_datadir}/nightscribe/version
%{_datadir}/nightscribe/docs
%{_datadir}/icons/hicolor/*/apps/nightscribe.png
%{_prefix}/lib/nightscribe/findorb

%changelog
* Sun Oct 11 2026 Francisco Jose Calvo Fernandez <irydeo@users.noreply.github.com> - %{version}-1
- First packaged build.
