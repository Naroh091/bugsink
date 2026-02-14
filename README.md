# Bugsink: Self-hosted Error Tracking

* [Error Tracking](https://www.bugsink.com/error-tracking/)
* [Built to self-host](https://www.bugsink.com/built-to-self-host/)
* [Sentry-SDK compatible](https://www.bugsink.com/connect-any-application/)
* [Scalable and reliable](https://www.bugsink.com/scalable-and-reliable/)

## About this fork

This fork extends Bugsink with a focus on **multi-project workflows**. Key improvements include:

- **Cross-project dashboard** -- A new overview dashboard that surfaces issues across all teams and projects, giving you a big-picture view of the state of things at a glance.
- **Reusable messaging services** -- Define Slack, Discord, or Mattermost webhooks once at the team level and attach them to any number of projects, instead of duplicating configuration per project.
- **Issue charts** -- Visual charts that show how issues behave over time, making it easier to spot trends and regressions.
- **Redesigned UI** -- Screens have been reworked to make better use of available space, keeping things clean and efficient as you navigate between projects.

For detailed documentation on these features, see the [docs/](docs/) folder.

A big thank you to [@vanschelven](https://github.com/vanschelven) for building Bugsink and making it open source. This fork wouldn't exist without that foundation.

-- David

### Installation & docs

The **quickest way to evaluate Bugsink** is to spin up a throw-away instance using Docker:

```
docker pull bugsink/bugsink:latest

docker run \
  -e SECRET_KEY=PUT_AN_ACTUAL_RANDOM_SECRET_HERE_OF_AT_LEAST_50_CHARS \
  -e CREATE_SUPERUSER=admin:admin \
  -e PORT=8000 \
  -p 8000:8000 \
  bugsink/bugsink
```

Visit [http://localhost:8000/](http://localhost:8000/), where you'll see a login screen. The default username and password
are `admin`.

Now, you can [set up your first project](https://www.bugsink.com/docs/quickstart/) and start tracking errors.

[Detailed installation instructions](https://www.bugsink.com/docs/installation/) are on the Bugsink website.

[More information and documentation](https://www.bugsink.com/)

