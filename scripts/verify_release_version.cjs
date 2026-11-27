// Exercise Release Please's actual updaters against a disposable release candidate.
// Install the matching test dependency first:
// npm install --prefix .tmp/release-check release-please@17.11.2 --no-audit --no-fund
// node scripts/verify_release_version.cjs .tmp/release-check
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const modules = path.resolve(process.argv[2] || '.tmp/release-check', 'node_modules');
const { GenericToml } = require(path.join(modules, 'release-please/build/src/updaters/generic-toml.js'));
const { PyProjectToml } = require(path.join(modules, 'release-please/build/src/updaters/python/pyproject-toml.js'));
const { Generic } = require(path.join(modules, 'release-please/build/src/updaters/generic.js'));
const yaml = require(path.join(modules, 'js-yaml'));
const { Version } = require(path.join(modules, 'release-please/build/src/version.js'));
const config = JSON.parse(fs.readFileSync(path.join(root, 'release-please-config.json'), 'utf8'));
const spec = config.packages['.']['extra-files'].find(file => file.path === 'uv.lock');
assert.equal(spec.type, 'toml');
const lock = fs.readFileSync(path.join(root, 'uv.lock'), 'utf8');
const project = fs.readFileSync(path.join(root, 'pyproject.toml'), 'utf8');
const citation = fs.readFileSync(path.join(root, 'CITATION.cff'), 'utf8');
const citationData = yaml.load(citation, { schema: yaml.JSON_SCHEMA });
const projectVersion = project.match(/^version = "([^"]+)"/m)[1];
assert.equal(citationData.version, projectVersion, 'citation must identify the package version');
const changelog = fs.readFileSync(path.join(root, 'CHANGELOG.md'), 'utf8');
const releaseHeading = changelog.split('\n').find(line => line.startsWith(`## [${projectVersion}]`));
assert.ok(releaseHeading, 'current version must have a changelog entry');
assert.equal(citationData['date-released'], releaseHeading.match(/\((\d{4}-\d{2}-\d{2})\)\s*$/)[1],
  'citation date must match the release changelog');
const citationSpec = config.packages['.']['extra-files'].find(file => file.path === 'CITATION.cff');
assert.equal(citationSpec.type, 'generic');
const version = Version.parse('0.99.0');
const releaseDate = new Date(2030, 0, 2, 12);
const updatedCitation = new Generic({ version, date: releaseDate }).updateContent(citation);
assert.equal(updatedCitation, citation
  .replace(/^version: .*$/m, 'version: 0.99.0 # x-release-please-version')
  .replace(/^date-released: .*$/m, 'date-released: 2030-01-02 # x-release-please-date'),
  'release updater must update citation version/date and preserve credits and other metadata');
const updatedLock = new GenericToml(spec.jsonpath, version).updateContent(lock);
const expectedLock = lock.replace(
  /(name = "climate-toolkit"\nversion = ")[^"]+("\n)/,
  (_, prefix, suffix) => `${prefix}0.99.0${suffix}`,
);
assert.notEqual(updatedLock, lock, 'release updater must change the project version');
assert.ok(updatedLock === expectedLock, 'dependency versions and lock formatting must stay unchanged');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'climate-release-version-'));
try {
  fs.writeFileSync(path.join(temporary, 'uv.lock'), updatedLock);
  fs.writeFileSync(path.join(temporary, 'pyproject.toml'), new PyProjectToml({ version }).updateContent(project));
  execFileSync('uv', ['lock', '--check', '--directory', temporary], { stdio: 'inherit' });
  console.log('Release Please updates project, lock and citation together; citation date and locked resolution pass.');
} finally {
  fs.rmSync(temporary, { recursive: true, force: true });
}
