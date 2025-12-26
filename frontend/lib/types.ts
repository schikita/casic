export type UserRole = "superadmin" | "table_admin" | "dealer";

export type User = {
  id: number;
  username: string;
  role: UserRole;
  table_id: number | null;
  is_active: boolean;
};

export type Table = {
  id: number;
  name: string;
  seats_count: number;
};

export type Session = {
  id: string;
  table_id: number;
  date: string;
  status: string;
  created_at: string;
};

export type Seat = {
  seat_no: number;
  player_name: string | null;
  total: number;
};
