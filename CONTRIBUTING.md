# Contributing to GhostStore

Thank you for your interest in contributing to GhostStore.

## What you can contribute

- Bug reports and bug fixes
- Documentation improvements
- New carrier type support
- Performance improvements to the core pipeline
- CLI and API improvements
- Test coverage

## What is out of scope for this repo

GhostStore Pro and Enterprise features (SQLite carrier, CDC chunking,
deduplication, cloud storage) are maintained separately and are not
part of this repository.

## How to report a bug

Open a GitHub Issue with:

- Your OS and Python version
- Steps to reproduce
- Expected vs actual behaviour
- Any error messages or tracebacks

## How to submit a pull request

1. Fork the repository
2. Create a branch: `git checkout -b fix/your-fix-name`
3. Make your changes
4. Run the test suite: `python -m pytest tests/test_v2.py -v`
5. Ensure all tests pass
6. Submit a pull request with a clear description of the change

## Code style

- Follow the existing code style — no external formatter required
- Keep functions focused and well-commented
- Add tests for any new functionality
- Do not add new dependencies without discussion

## Security issues

Do not open public GitHub Issues for security vulnerabilities.
Contact via GitHub private message instead.

## Licence

By submitting a pull request, you agree that your contribution will be
licensed under the same GPL v3 licence as the rest of the project.

---

_GhostStore — github.com/JamesPaul777/ghoststore_
