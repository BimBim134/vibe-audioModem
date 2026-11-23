# Security policy

## Reporting a vulnerability

Please do not open a public issue for a security problem. Use GitHub's private reporting instead: on the repository page, open **Security**, then **Report a vulnerability**. You will get an answer as soon as the maintainer can read it.

## What is in scope

The application runs a small web server that listens on the loopback address (`127.0.0.1`) only. Anything that lets another machine, or another web page, reach it or read files through it is in scope, and so is a crash or a wrong Message accepted on crafted audio.

## Supported versions

Only the latest release and the `main` branch are supported.
