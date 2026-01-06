export type UserRole = "superadmin" | "table_admin" | "dealer" | "waiter";

export type User = {
  id: number;
  username: string;
  role: UserRole;
  table_id: number | null;
  is_active: boolean;
  hourly_rate: number | null;
};

export type Table = {
  id: number;
  name: string;
  seats_count: number;
};

export type Staff = {
  id: number;
  username: string;
  role: UserRole;
};

export type Session = {
  id: string;
  table_id: number;
  date: string;
  status: string;
  created_at: string;
  dealer_id: number | null;
  waiter_id: number | null;
  dealer: Staff | null;
  waiter: Staff | null;
};

export type Seat = {
  seat_no: number;
  player_name: string | null;
  total: number;
};
