DROP TABLE operations;

CREATE TABLE
  operations (
    ID int,
    year varchar(4),
    opn varchar(255),
    date date,
    dt_exit datetime,
    dt_close datetime,
    typology varchar(500),
    x varchar(255),
    y varchar(255),
    loc varchar(255),
    boss varchar(255),
    address varchar(255),
    caller varchar(255),
    operator varchar(255),
    PRIMARY KEY (ID, year)
  );

DROP TABLE starts;

CREATE TABLE
  starts (
    OpID int,
    ID int,
    year varchar(4),
    vehicle varchar(255),
    exit_dt datetime,
    inplace_dt datetime,
    back_dt datetime,
    boss varchar(255),
    PRIMARY KEY (OpID, ID, year)
  );

DROP TABLE staff;

CREATE TABLE
  staff (
    ID int,
    name varchar(100),
    surname varchar(100),
    role varchar(4),
    status int,
    photo varchar(255),
    phone varchar(20),
    radio int,
    birthday date,
    start date,
    license int,
    license_exp date,
    medical date,
    address varchar(255),
    weekend_shift int,
    week_shift int,
    PRIMARY KEY (ID)
  );

CREATE OR REPLACE VIEW staffExp AS
SELECT
  s.ID,
  s.name,
  s.surname,
  s.role,
  s.photo,
  s.phone,
  s.radio,
  s.birthday,
  s.start,
  s.license,
  s.license_exp,
  s.medical,
  s.address,
  CASE
    WHEN s.status = 0 THEN 'RITIRATO'
    ELSE 'ATTIVO'
  END AS status_label,
  DATE_ADD(
    DATE_ADD(s.medical, INTERVAL 2 YEAR),
    INTERVAL 6 MONTH
  ) AS medical_exp,
  CONCAT(
    CASE s.week_shift
      WHEN 1 THEN 'Lunedì'
      WHEN 2 THEN 'Martedì'
      WHEN 3 THEN 'Mercoledì'
      WHEN 4 THEN 'Giovedì'
      WHEN 5 THEN 'Venerdì'
      ELSE 'Sconosciuto'
    END,
    ' - ',
    COALESCE((
      SELECT GROUP_CONCAT(
        CONCAT(o.surname, ' ', LEFT(o.name, 1), '.')
        ORDER BY o.surname SEPARATOR ' / '
      )
      FROM staff o
      WHERE o.week_shift = s.week_shift
      AND o.id != s.id
    ), '—')
  ) AS week_shift_members,
  CONCAT(
    'Turno ',
    s.weekend_shift,
    ' - ',
    COALESCE((
      SELECT GROUP_CONCAT(
        CONCAT(o.surname, ' ', LEFT(o.name, 1), '.')
        ORDER BY o.surname SEPARATOR ' / '
      )
      FROM staff o
      WHERE o.weekend_shift = s.weekend_shift
      AND o.id != s.id
    ), '—')
  ) AS weekend_shift_members
FROM staff s;