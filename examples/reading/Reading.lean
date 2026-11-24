/- Source-reading fixture. These declarations exercise navigation and comparison. -/
namespace Reading

def Positive (n : Nat) : Prop := 0 < n
def Nonnegative (n : Nat) : Prop := 0 ≤ n

theorem keep_positive (n : Nat) (h : Positive n) : Positive n := by
  exact h

theorem keep_nonnegative (n : Nat) (h : Nonnegative n) : Nonnegative n := by
  exact h

theorem forward_positive (n : Nat) (h : Positive n) : Positive n := by
  exact keep_positive n h

def labelA : String := "a b"
def labelB : String := "a  b"

end Reading

namespace Other

theorem forward_positive : True := by
  exact True.intro

end Other
