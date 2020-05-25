# FeatherLight API

FeatherLight is a GraphQL API for interacting with a custodial Bitcoin Lightning Network node. The node supports many users and handles the transfer of funds internally with an accounting system and externally via regular lightning network payments.

FeatherLight also supports GraphQL subscriptions for sending realtime payment data to any device capable of websocket connections. This is intended to enable both real-time browser based payments in any website, as well as enabling IoT devices to accept and manage payments without having to run a lightning node locally.

The repo is a fully featured FeatherLight setup which automatically builds everything from bitcoin core, lnd, lndmon and the GraphQL server. It is possible to use the bitcoin backend of your choice (btcd, neutrino, etc.) but these are not configured nor tested.

FeatherLight has many dependencies in many different languages. Docker is the best way to get a node up and running.

#### Setup

1. git clone https://github.com/FeatherLightApp/FeatherLight-API
2. cd FeatherLight-API
3. mv .env1 .env
4. Configure desired settings in global.env and .env
5. docker-compose up -d


### Reponsible Disclosure

This software is responsible for handling and transfering valuable Bitcoins. If you have found a vulnerability in the software please email me at hello@seanaye.ca. 

### TODOs

- split admin routes into secondary service and federate it
- ~~fix zmqpubhashblock port binding~~
- ~~subclass graphql to provide http only refresh macaroons on token payload responses~~
- ~~change from jwt to macaroons~~
- CHANGE TO DEFAULT ENUM TYPES ON ARIADNE 0.12 RELEASE
- ~~switch from hex data to bytea in postgres~~
- ~~restructure context object~~
- ~~consolidate DB_User and UserAPI~~
- ~~remove protobuf to dict~~
- add support for lnurl
- add hold invoices
- ~~restructure schema~~
- ~~write subscriptions~~
- ~~consolidate configs into global config~~
- mypy type checking - in progress
- write more app level tests
- ~~switch to argon2 cffi password hashing~~
- ~~restructure code directory~~
- ~~create simple frontend for api~~
