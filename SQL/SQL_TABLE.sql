DROP TABLE Operations;
CREATE TABLE Operations (
  ID       int,
  year     varchar(4),
  opn     varchar(255),
  date     date,
  dt_exit    datetime,
  dt_close   datetime,
  typology varchar(500),
  x        varchar(255),
  y        varchar(255),
  loc      varchar(255),
  boss     varchar(255),
  address  varchar(255),
  caller   varchar(255),
  operator varchar(255),
  PRIMARY KEY(ID, year)
);

DROP TABLE Starts;
CREATE TABLE Starts (
  OpID     int,
  ID       int,
  year     varchar(4),
  vehicle       varchar(255),
  exit_dt     datetime,
  inplace_dt  datetime,
  back_dt     datetime,
  boss     varchar(255),
  PRIMARY KEY(OpID, ID, year)
);